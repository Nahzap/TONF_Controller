"""Medidas de solo lectura sobre un enlace ya abierto."""

from __future__ import annotations

from tonf.link import Link
from tonf.model import Indicator
from tonf.parse import (
    looks_halted,
    looks_like_grbl,
    looks_like_marlin,
    parse_grbl_banner,
    parse_m115,
    parse_m119,
    percentile,
)
from tonf.ports import PortInfo


def _ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def _stats(samples: list[float]) -> str:
    if not samples:
        return "sin respuestas"
    return (
        f"n={len(samples)}, "
        f"mín {_ms(min(samples))}, "
        f"mediana {_ms(percentile(samples, 0.5))}, "
        f"p95 {_ms(percentile(samples, 0.95))}, "
        f"máx {_ms(max(samples))}"
    )


def identify(link: Link, greeting: list[str]) -> tuple[str, Indicator]:
    """Devuelve 'marlin', 'grbl' o 'desconocido' y el indicador de identidad."""

    if looks_like_grbl(greeting):
        info = parse_grbl_banner(greeting)
        extra = link.transact("$I", timeout=1.5)
        info.update(parse_grbl_banner(extra.lines))
        text = ", ".join(f"{key}={value}" for key, value in info.items()) or "banner grbl"
        halt = "El firmware arrancó en alarma o error." if looks_halted(extra.lines) else ""
        return "grbl", Indicator(
            "identidad",
            "Identidad del firmware",
            "medido",
            text,
            "Banner de conexión y $I. No se envió homing ni G-code de movimiento.",
            halt,
        )

    identity = link.transact("M115", timeout=2.0)
    blob = greeting + identity.lines
    if looks_like_marlin(blob) or any(line.startswith("FIRMWARE_NAME:") for line in identity.lines):
        fields = parse_m115(identity.lines)
        text = ", ".join(f"{key}={value}" for key, value in fields.items()) or "respuesta Marlin"
        limitante = ""
        if looks_halted(blob):
            limitante = (
                "El firmware está detenido por temperatura. Con los zócalos vacíos hay que "
                "compilar sin termistores; si no, Marlin no acepta movimiento aunque el USB viva."
            )
        return "marlin", Indicator(
            "identidad",
            "Identidad del firmware",
            "medido",
            text,
            f"M115 en {link.name} a {link.baud} baudios. {_ms(identity.seconds)}.",
            limitante,
        )

    if looks_like_grbl(identity.lines):
        return identify(link, identity.lines)

    preview = " | ".join(blob[:6]) or "silencio"
    return "desconocido", Indicator(
        "identidad",
        "Identidad del firmware",
        "bloqueado",
        preview,
        "No hubo FIRMWARE_NAME ni banner grbl. El USB CDC a veces ignora el baudrate; se probaron 115200 y 250000.",
        "Sin firmware que hable texto, este host no puede medir finales, latencia ni capacidades. Klipper usa un protocolo binario: si el producto USB dice Klipper, el host de estas pruebas no lo implementa.",
    )


def measure_latency(link: Link, protocol: str, samples: int) -> Indicator:
    command = "M114" if protocol == "marlin" else "?"
    times: list[float] = []
    timeouts = 0
    for _ in range(samples):
        exchange = link.transact(command, timeout=1.0)
        if exchange.timed_out:
            timeouts += 1
            continue
        times.append(exchange.seconds)
    if not times:
        return Indicator(
            "latencia",
            "Latencia de ida y vuelta",
            "bloqueado",
            f"{timeouts} timeouts de {samples} con {command}",
            "Cada muestra es un comando de solo lectura y la espera hasta ok o error.",
            "El enlace no cierra la respuesta. No tiene sentido subir la tasa.",
        )
    limitante = ""
    if timeouts:
        limitante = f"{timeouts} de {samples} muestras no terminaron en ok/error."
    elif percentile(times, 0.95) > 0.1:
        limitante = "La p95 pasa de 100 ms. Sirve para leer estado; es pobre como lazo de posición."
    return Indicator(
        "latencia",
        "Latencia de ida y vuelta",
        "medido",
        _stats(times),
        f"Comando {command}, una transacción cada vez, sin encadenar.",
        limitante,
    )


def measure_burst(link: Link, protocol: str) -> Indicator:
    command = "M119" if protocol == "marlin" else "$I"
    count = 8
    started_ok = 0
    lines: list[str] = []
    # Ocho comandos cortos, todavía de uno en uno: mide el techo útil del
    # diálogo, no un chorro que desborde el buffer de 128 bytes de Marlin.
    times: list[float] = []
    for _ in range(count):
        exchange = link.transact(command, timeout=1.0)
        lines.extend(exchange.lines)
        if not exchange.timed_out:
            started_ok += 1
            times.append(exchange.seconds)
    if looks_halted(lines):
        return Indicator(
            "tasa",
            "Ráfaga de comandos de estado",
            "medido",
            f"{started_ok}/{count} respuestas",
            _stats(times),
            "El firmware reportó parada térmica durante la ráfaga.",
        )
    rate = ""
    if times:
        total = sum(times)
        rate = f", {count / total:.1f} comandos/s sostenidos" if total else ""
    return Indicator(
        "tasa",
        "Ráfaga de comandos de estado",
        "medido" if started_ok else "bloqueado",
        f"{started_ok}/{count} respuestas{rate}",
        f"Comando {command}. No se mandó G0/G1 ni se encendió ninguna salida.",
        "" if started_ok == count else "La ráfaga no se completó. El buffer serie o el firmware están limitando el diálogo.",
    )


def measure_endstops(link: Link, protocol: str) -> Indicator:
    if protocol != "marlin":
        exchange = link.transact("?", timeout=1.0)
        text = " | ".join(exchange.lines) or "sin estado"
        return Indicator(
            "finales",
            "Finales de carrera",
            "medido" if not exchange.timed_out else "bloqueado",
            text,
            "Estado grbl con '?'. Nada cableado en X-STOP, Y-STOP, Z-STOP, E0DET ni E1DET.",
            "Un final que figure activo con el pin al aire suele ser lógica invertida o el pin DIAG del módulo, que aquí no está puesto.",
        )
    exchange = link.transact("M119", timeout=1.5)
    states = parse_m119(exchange.lines)
    if exchange.timed_out or not states:
        preview = " | ".join(exchange.lines) or "sin respuesta"
        return Indicator(
            "finales",
            "Finales de carrera",
            "bloqueado",
            preview,
            "M119 con los conectores vacíos.",
            "",
        )
    text = ", ".join(f"{name}={state}" for name, state in states.items())
    triggered = [name for name, state in states.items() if state.lower() not in {"open", "abierto"}]
    limitante = ""
    if triggered:
        limitante = (
            "Con nada conectado, estos figuran activos: "
            + ", ".join(triggered)
            + ". En Marlin eso depende de la inversión del pin; no es una medida de un interruptor."
        )
    return Indicator(
        "finales",
        "Finales de carrera",
        "medido",
        text,
        "M119. Pines de placa: X P1.29, Y P1.28, Z P1.27, E0 P1.26, E1 P1.25, todos con pull-up a 3,3 V.",
        limitante,
    )


def measure_position(link: Link, protocol: str) -> Indicator:
    if protocol != "marlin":
        return Indicator(
            "posicion",
            "Posición reportada",
            "bloqueado",
            "grbl no se consultó con un G-code de estado de ejes",
            "El '?' de la latencia ya trae la línea de estado. No se envió G0.",
            "",
        )
    exchange = link.transact("M114", timeout=1.5)
    text = next((line for line in exchange.lines if line.startswith("X:")), "")
    if exchange.timed_out or not text:
        return Indicator(
            "posicion",
            "Posición reportada",
            "bloqueado",
            " | ".join(exchange.lines) or "sin M114",
            "M114 no mueve el motor; solo lee contadores del firmware.",
            "",
        )
    return Indicator(
        "posicion",
        "Posición reportada",
        "medido",
        text,
        "Contadores internos. Con los drivers sin montar no dicen nada del eje mecánico.",
        "Open loop: esta cifra no es una posición medida.",
    )


def port_indicator(ports: list[PortInfo], chosen: list[PortInfo], reason: str) -> Indicator:
    if not ports:
        valor = "ningún puerto serie"
    else:
        valor = "; ".join(
            f"{port.device} ({port.description or port.product or 'sin descripción'})"
            for port in ports
        )
    estado = "medido" if chosen else "bloqueado"
    return Indicator(
        "usb",
        "Enumeración USB",
        estado,
        valor,
        reason,
        "" if chosen else "Sin este enlace el resto de pruebas de diálogo quedan bloqueadas.",
    )


def live_indicators(link: Link, greeting: list[str], samples: int) -> list[Indicator]:
    protocol, identity = identify(link, greeting)
    found = [
        Indicator(
            "protocolo",
            "Protocolo",
            "medido" if protocol != "desconocido" else "bloqueado",
            protocol,
            f"{link.name} abierto a {link.baud}. El USB CDC de esta placa suele ignorar el baudrate; 115200 es el del manual BTT y 250000 el defecto de Marlin.",
            "Abrir el puerto en Windows suele reiniciar el MCU por DTR.",
        ),
        identity,
    ]
    if protocol == "desconocido":
        for item_id, title in (
            ("latencia", "Latencia de ida y vuelta"),
            ("tasa", "Ráfaga de comandos de estado"),
            ("finales", "Finales de carrera"),
            ("posicion", "Posición reportada"),
        ):
            found.append(
                Indicator(
                    item_id,
                    title,
                    "bloqueado",
                    "sin protocolo",
                    "Hace falta una respuesta Marlin o grbl.",
                    "",
                )
            )
        return found
    found.append(measure_latency(link, protocol, samples))
    found.append(measure_burst(link, protocol))
    found.append(measure_endstops(link, protocol))
    found.append(measure_position(link, protocol))
    return found
