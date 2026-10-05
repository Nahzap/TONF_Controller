"""Prueba en vacío del motor de E1 (CF3925-100-SL). No hace home.

La corriente queda en 800 mA, el tope de protección. Hace falta el
Marlin con EXTRUDERS 2 y E1_DRIVER_TYPE TMC2209.

Uso, desde D:\\TONF_Controller:

    .\\.venv\\Scripts\\python.exe .\\scripts\\prueba_motor_e1.py
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
        ("M302 S0", 3),
        ("M412 S0", 3),
        ("M203 X100 Y100 Z20 E25", 3),
        ("M906 X450", 3),
        ("M906 Y800", 3),
        ("M906 Z800", 3),
        ("M906 E800", 3),
        ("T1", 3),
        ("M906 T1 E800", 3),
        ("M500", 4),
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
        ("M119", 3),
        ("M18", 3),
        ("T0", 3),
    ]
    for command, timeout in steps:
        body = transact(port, command, timeout)
        print(f"\n===== {command} =====")
        print(body or "(sin respuesta)")
        lowered = body.lower()
        if "unknown command" in lowered or "cold extrusion" in lowered or "invalid extruder" in lowered or body.startswith("Error"):
            print("DETENIDO")
            break
    port.close()


if __name__ == "__main__":
    main()
