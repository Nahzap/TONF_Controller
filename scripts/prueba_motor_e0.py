"""Prueba en vacío del canal E0 (SY42STH38-1684A). No hace home.

E0 es la herramienta T0 y se mueve con la letra E. La corriente queda
en 800 mA. M302 S0 permite ese movimiento con el hotend frío.
StallGuard se escribe con M914 T0 E.

Uso, desde D:\\TONF_Controller:

    .\\.venv\\Scripts\\python.exe .\\scripts\\prueba_motor_e0.py
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
    print("Canal E0.", flush=True)
    print(f"Prueba en {PORT} a {BAUD} baudios.", flush=True)
    print("Abriendo el puerto. Eso reinicia la placa.", flush=True)
    port = serial.Serial(PORT, BAUD, timeout=0.3, write_timeout=2)
    time.sleep(1.0)
    port.reset_input_buffer()
    steps = [
        ("M114", 3),
        ("M302 S0", 3),
        ("T0", 3),
        ("M906 T0 E800", 3),
        ("M914 T0 E100", 3),
        ("M906", 3),
        ("M83", 3),
        ("G92 E150", 3),
        ("G1 E10 F300", 5),
        ("M400", 20),
        ("G1 E-10 F300", 5),
        ("M400", 20),
        ("G1 E40 F600", 5),
        ("M400", 25),
        ("G1 E-40 F600", 5),
        ("M400", 25),
        ("G1 E40 F1800", 5),
        ("M400", 20),
        ("G1 E-40 F1800", 5),
        ("M400", 20),
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
        lowered = body.lower()
        if "unknown command" in lowered or "cold extrusion" in lowered or body.startswith("Error"):
            print("DETENIDO", flush=True)
            break
    port.close()


if __name__ == "__main__":
    main()
