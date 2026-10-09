"""Prueba en vacío del motor de Z. No hace home.

Stepper de baja potencia. Cada bobina mide 45 Ω. La consigna es 450 mA.
M906 lleva el número compensado por la Rsense. A 12 V la bobina no alcanza esos 450 mA.

Uso, desde D:\\TONF_Controller:

    .\\.venv\\Scripts\\python.exe .\\scripts\\prueba_motor_z.py
"""

import sys
import time

import serial

PORT = "COM3"
BAUD = 115200


def _accepted(text: str) -> bool:
    return any(line == "ok" or line.startswith("ok ") for line in text.splitlines())


def transact(port: serial.Serial, command: str, timeout: float) -> str:
    port.write((command + "\n").encode("ascii"))
    port.flush()
    end = time.time() + timeout
    chunks: list[bytes] = []
    shown = 0

    def text() -> str:
        return b"".join(chunks).decode("utf-8", "replace").replace("\r", "")

    def emit(final: bool) -> None:
        nonlocal shown
        body = text()
        limit = len(body) if final else body.rfind("\n") + 1
        if limit <= shown:
            return
        chunk = body[shown:limit]
        shown = limit
        print(chunk, end="" if chunk.endswith("\n") else "\n", flush=True)

    while time.time() < end:
        block = port.read(4096)
        if not block:
            if _accepted(text()):
                break
            continue
        chunks.append(block)
        emit(False)
        if _accepted(text()):
            time.sleep(0.05)
            extra = port.read(4096)
            if extra:
                chunks.append(extra)
                emit(False)
            break
    emit(True)
    return text().strip()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    print(f"Prueba en {PORT} a {BAUD} baudios.", flush=True)
    print("Abriendo el puerto. Eso reinicia la placa.", flush=True)
    port = serial.Serial(PORT, BAUD, timeout=0.3, write_timeout=2)
    time.sleep(1.0)
    port.reset_input_buffer()
    steps = [
        ("M114", 3),
        ("M906 Z713", 3),
        ("M914 Z100", 3),
        ("M500", 4),
        ("M906", 3),
        ("G90", 3),
        ("G92 Z150", 3),
        ("G91", 3),
        ("G1 Z10 F300", 5),
        ("M400", 20),
        ("G1 Z-10 F300", 5),
        ("M400", 20),
        ("G1 Z40 F600", 5),
        ("M400", 25),
        ("G1 Z-40 F600", 5),
        ("M400", 25),
        ("G1 Z40 F1800", 5),
        ("M400", 20),
        ("G1 Z-40 F1800", 5),
        ("M400", 20),
        ("G90", 3),
        ("M114", 3),
        ("M122", 6),
        ("M914", 3),
        ("M119", 3),
        ("M18", 3),
    ]
    for command, timeout in steps:
        print(f"\n===== {command} =====", flush=True)
        body = transact(port, command, timeout)
        if not body:
            print("(sin respuesta)", flush=True)
        if "Unknown command" in body or body.startswith("Error"):
            print("DETENIDO", flush=True)
            break
    port.close()


if __name__ == "__main__":
    main()
