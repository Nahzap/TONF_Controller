"""Abre la SKR, corre las medidas y arma el informe."""

from __future__ import annotations

from tonf.link import Link, candidate_bauds, open_serial
from tonf.measure import live_indicators, port_indicator
from tonf.model import Indicator, Suite
from tonf.parse import looks_like_grbl, looks_like_marlin
from tonf.ports import PortInfo, from_list_port, selectable
from tonf.reference import REFERENCE


def list_ports() -> list[PortInfo]:
    from serial.tools import list_ports

    ports = [from_list_port(raw) for raw in list_ports.comports()]
    return [port for port in ports if "bluetooth" not in port.blob]


def _greeting_is_alive(lines: list[str]) -> bool:
    blob = "\n".join(lines).lower()
    return "start" in blob or looks_like_marlin(lines) or looks_like_grbl(lines)


def connect(ports: list[PortInfo], requested: str | None, baud: int | None) -> tuple[Link | None, list[str], str]:
    chosen, reason = selectable(ports, requested)
    notes = [reason]
    if not chosen:
        return None, notes, reason
    port = chosen[0]
    errors: list[str] = []
    for rate in candidate_bauds(baud):
        handle = None
        try:
            handle = open_serial(port.device, rate)
            link = Link(handle, rate, port.device)
            greeting = link.drain(2.0)
            if _greeting_is_alive(greeting) or rate == candidate_bauds(baud)[-1]:
                link.transcript.insert(0, f"# greeting {port.device} @ {rate}")
                for line in greeting:
                    if f"<< {line}" not in link.transcript:
                        link.transcript.append(f"<< {line}")
                notes.append(f"Abierto {port.device} a {rate} baudios.")
                return link, notes, reason
            link.close()
        except OSError as exc:
            errors.append(f"{port.device} @ {rate}: {exc}")
            if handle is not None:
                close = getattr(handle, "close", None)
                if close is not None:
                    close()
    if errors:
        notes.extend(errors)
    return None, notes, reason


def run(requested: str | None = None, baud: int | None = None, samples: int = 20) -> Suite:
    ports = list_ports()
    chosen, reason = selectable(ports, requested)
    suite = Suite()
    suite.indicators.append(port_indicator(ports, chosen, reason))
    link, notes, _reason = connect(ports, requested, baud)
    suite.notes.extend(notes)
    if link is None:
        detail = notes[-1] if notes else reason
        for item_id, title in (
            ("protocolo", "Protocolo"),
            ("identidad", "Identidad del firmware"),
            ("latencia", "Latencia de ida y vuelta"),
            ("tasa", "Ráfaga de comandos de estado"),
            ("finales", "Finales de carrera"),
            ("posicion", "Posición reportada"),
        ):
            suite.indicators.append(Indicator(item_id, title, "bloqueado", "sin enlace", detail, ""))
    else:
        try:
            greeting = [line.removeprefix("<< ").strip() for line in link.transcript if line.startswith("<< ")]
            suite.indicators.extend(live_indicators(link, greeting, samples))
            suite.transcript.extend(link.transcript)
        finally:
            link.close()
    suite.indicators.extend(REFERENCE)
    suite.notes.append(
        "Para hablar sin motores: 5V SEL entre USB y +5V, cable de datos, LED D5 encendido. "
        "VMOT sigue apagado y el UART de un TMC2209 no responde en ese estado."
    )
    return suite
