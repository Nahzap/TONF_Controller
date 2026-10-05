"""Línea de comandos del banco.

    .venv\\Scripts\\python.exe -m tonf suite --listar
    .venv\\Scripts\\python.exe -m tonf suite
    .venv\\Scripts\\python.exe -m tonf puertos
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from tonf import __version__
from tonf.gcode import load_gcode, stream_program
from tonf.parse import looks_like_grbl
from tonf.reference import REFERENCE
from tonf.report import render, write_report
from tonf.session import connect, list_ports, run


def _configure_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


def _build() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tonf",
        description="Host para la BTT SKR V1.4 Turbo. El firmware medido en la placa es Marlin.",
    )
    parser.add_argument("--version", action="version", version=f"tonf {__version__}")
    commands = parser.add_subparsers(dest="comando", required=True)

    commands.add_parser("puertos", help="Lista los USB serie sin abrirlos.")
    commands.add_parser("referencia", help="Límites de documentación, sin tocar la placa.")
    commands.add_parser("firmware", help="Qué firmware contestó la placa y cómo hablarle.")

    enviar = commands.add_parser(
        "enviar",
        help="Envía un archivo de G-code con el protocolo de grbl (línea y ok).",
    )
    enviar.add_argument("archivo", type=Path, help="Programa .nc, .gcode o .ngc ya existente.")
    enviar.add_argument("--port", help="Puerto COM. Obligatorio si hay varios USB serie.")
    enviar.add_argument("--baud", type=int, help="Baudrate. grblHAL usa 115200; el USB CDC suele ignorarlo.")
    enviar.add_argument(
        "--comprobar",
        action="store_true",
        help="Activa el modo $C de grbl: analiza el G-code y no mueve motores.",
    )
    enviar.add_argument(
        "--vista",
        action="store_true",
        help="Muestra las líneas que se enviarían, sin abrir el puerto.",
    )
    enviar.add_argument(
        "--forzar",
        action="store_true",
        help="Envía aunque el banner no sea Grbl. El firmware actual de la placa puede no ser grblHAL.",
    )
    enviar.add_argument(
        "--espera",
        type=float,
        default=120.0,
        help="Segundos máximos de espera del ok de cada línea.",
    )

    suite = commands.add_parser(
        "suite",
        help="Carga config/banco.toml y mueve los canales activos, en orden.",
    )
    suite.add_argument("--config", type=Path, help="Otro archivo TOML. Por defecto config/banco.toml.")
    suite.add_argument("--canal", help="Mueve solo ese canal: X, Y, Z, E0 o E1.")
    suite.add_argument("--listar", action="store_true", help="Muestra las señales y no abre el puerto.")
    suite.add_argument("--comandos", action="store_true", help="Muestra el G-code y no abre el puerto.")

    live = commands.add_parser(
        "indicadores",
        help="Mide enlace, latencia, finales y posición reportada.",
    )
    live.add_argument("--port", help="Puerto COM concreto. Obligatorio si hay varios USB serie.")
    live.add_argument("--baud", type=int, help="Fija el baudrate. Por defecto prueba 115200 y 250000.")
    live.add_argument("--muestras", type=int, default=20, help="Repeticiones de la medida de latencia.")
    live.add_argument(
        "--salida",
        type=Path,
        default=Path("reports"),
        help="Carpeta del informe markdown.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    args = _build().parse_args(argv)
    if args.comando == "puertos":
        ports = list_ports()
        if not ports:
            print("No hay puertos serie (Bluetooth omitido).")
            return 1
        for port in ports:
            vid = f"{port.vid:04X}:{port.pid:04X}" if port.vid is not None and port.pid is not None else "sin VID"
            print(f"{port.device}\t{vid}\t{port.description}")
        return 0
    if args.comando == "referencia":
        for item in REFERENCE:
            print(f"[{item.estado}] {item.titulo}: {item.valor}")
            if item.limitante:
                print(f"  limitante: {item.limitante}")
        return 0
    if args.comando == "firmware":
        print(_FIRMWARE)
        return 0
    if args.comando == "enviar":
        return _enviar(args)
    if args.comando == "suite":
        return _suite(args)

    if args.muestras < 1:
        print("--muestras tiene que ser al menos 1.")
        return 2
    suite = run(requested=args.port, baud=args.baud, samples=args.muestras)
    moment = datetime.now()
    print(render(suite, moment))
    path = write_report(suite, args.salida, moment)
    print(f"Informe: {path}")
    blocked = any(item.id == "protocolo" and item.estado == "bloqueado" for item in suite.indicators)
    return 1 if blocked else 0


_FIRMWARE = """\
La placa corre Marlin 2.1.2, máquina «TONF SKR», compilado el 5 de octubre de 2026.
Puerto COM3, 115200 baudios. Identidad: M115.
Cinco drivers TMC2209: X, Y, Z, E0 y E1. E0 es T0 y E1 es T1; los dos se mueven con la letra E. Las señales están en config/banco.toml.
La guía de uso es Docs/2026-10-05_1646_guia-suite-motores.md.

tonf suite aplica ese archivo y mueve los canales en orden.
tonf enviar sigue el protocolo de grbl y no manda un archivo a este Marlin.
"""


def _suite(args: argparse.Namespace) -> int:
    from tonf.banco import ConfigError, build, describe, format_program, load_path, run

    try:
        bench = load_path(args.config)
        if args.listar:
            print(describe(bench, args.canal))
        if args.comandos:
            if args.listar:
                print()
            print(format_program(build(bench, args.canal)))
        if args.listar or args.comandos:
            return 0
        return run(bench, args.canal)
    except ConfigError as exc:
        print(exc)
        return 2


def _enviar(args: argparse.Namespace) -> int:
    if not args.archivo.is_file():
        print(f"No está el archivo {args.archivo}.")
        return 2
    lines = load_gcode(args.archivo)
    if not lines:
        print("El archivo no tiene líneas de G-code.")
        return 2
    if args.vista:
        for line in lines:
            print(line)
        return 0
    ports = list_ports()
    link, notes, _reason = connect(ports, args.port, args.baud)
    for note in notes:
        print(note)
    if link is None:
        return 1
    try:
        greeting = [line.removeprefix("<< ").strip() for line in link.transcript if line.startswith("<< ")]
        if not looks_like_grbl(greeting) and not args.forzar:
            print(
                "El puerto no presentó un banner Grbl/grblHAL. "
                "No se envió el archivo. El firmware instalado es Marlin y este envío espera el protocolo grbl."
            )
            return 1
        result = stream_program(link, lines, comprobar=args.comprobar, timeout=args.espera)
    finally:
        link.close()
    print(f"Líneas aceptadas: {result.ok} de {len(lines)}.")
    if result.stopped:
        print(result.stopped)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
