"""Prueba en vacío del motor de X. No hace home.

Uso, desde D:\\TONF_Controller:

    .\\.venv\\Scripts\\python.exe .\\scripts\\prueba_motor_x.py
"""

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
    chunks = []
    while time.time() < end:
        block = port.read(4096)
        if not block:
            text = b"".join(chunks).decode("utf-8", "replace").replace("\r", "")
            if _accepted(text):
                break
            continue
        chunks.append(block)
        text = b"".join(chunks).decode("utf-8", "replace").replace("\r", "")
        if _accepted(text):
            time.sleep(0.05)
            extra = port.read(4096)
            if extra:
                chunks.append(extra)
            break
    return b"".join(chunks).decode("utf-8", "replace").replace("\r", "").strip()


def main() -> None:
    port = serial.Serial(PORT, BAUD, timeout=0.3, write_timeout=2)
    time.sleep(1.0)
    port.reset_input_buffer()
    steps = [
        ("M114", 3),
        ("M906 X450", 3),
        ("M906", 3),
        ("G90", 3),
        ("G92 X150", 3),
        ("G91", 3),
        ("G1 X10 F300", 5),
        ("M400", 20),
        ("G1 X-10 F300", 5),
        ("M400", 20),
        ("G1 X40 F600", 5),
        ("M400", 25),
        ("G1 X-40 F600", 5),
        ("M400", 25),
        ("G1 X40 F1800", 5),
        ("M400", 20),
        ("G1 X-40 F1800", 5),
        ("M400", 20),
        ("G90", 3),
        ("M114", 3),
        ("M122", 6),
        ("M119", 3),
        ("M18", 3),
    ]
    for command, timeout in steps:
        body = transact(port, command, timeout)
        print(f"\n===== {command} =====")
        print(body or "(sin respuesta)")
        if "Unknown command" in body or body.startswith("Error"):
            print("DETENIDO")
            break
    port.close()


if __name__ == "__main__":
    main()
