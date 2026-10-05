"""Sesión serie de solo lectura."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from tonf.guard import guard
from tonf.parse import is_terminator

_BAUDS = (115200, 250000)


@dataclass
class Exchange:
    command: str
    lines: list[str]
    seconds: float
    timed_out: bool


class Link:
    """Puerto ya abierto. `readline` debe devolver bytes y respetar un timeout corto."""

    def __init__(self, port: object, baud: int, name: str) -> None:
        self.port = port
        self.baud = baud
        self.name = name
        self.transcript: list[str] = []

    def transact(self, command: str, timeout: float = 1.5) -> Exchange:
        return self.exchange(guard(command), timeout)

    def exchange(self, command: str, timeout: float = 1.5) -> Exchange:
        """Envía una línea ya aceptada. El envío de G-code no pasa por el filtro de solo lectura."""
        safe = command.strip()
        payload = (safe + "\n").encode("ascii")
        started = time.perf_counter()
        self.port.write(payload)  # type: ignore[attr-defined]
        flush = getattr(self.port, "flush", None)
        if flush is not None:
            flush()
        lines: list[str] = []
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            raw = self.port.readline()  # type: ignore[attr-defined]
            if not raw:
                continue
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            lines.append(text)
            self.transcript.append(f"<< {text}")
            if is_terminator(text):
                break
        seconds = time.perf_counter() - started
        self.transcript.append(f">> {safe} ({seconds * 1000:.1f} ms)")
        return Exchange(safe, lines, seconds, timed_out=not lines or not is_terminator(lines[-1]))

    def drain(self, seconds: float) -> list[str]:
        lines: list[str] = []
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            raw = self.port.readline()  # type: ignore[attr-defined]
            if not raw:
                continue
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            lines.append(text)
            self.transcript.append(f"<< {text}")
        return lines

    def close(self) -> None:
        close = getattr(self.port, "close", None)
        if close is not None:
            close()


@dataclass
class ScriptedPort:
    """Puerto falso: cada escritura recibe las líneas programadas."""

    replies: dict[str, list[str]]
    greeting: list[str] = field(default_factory=list)
    timeout_commands: frozenset[str] = frozenset()
    written: list[str] = field(default_factory=list)
    _queue: list[str] = field(default_factory=list)

    def write(self, payload: bytes) -> None:
        command = payload.decode("ascii").strip()
        self.written.append(command)
        if command in self.timeout_commands:
            self._queue = []
            return
        self._queue.extend(self.replies.get(command, ["ok"]))

    def flush(self) -> None:
        return None

    def reset_input_buffer(self) -> None:
        self._queue.clear()

    def readline(self) -> bytes:
        if self.greeting:
            line = self.greeting.pop(0)
            return (line + "\n").encode("utf-8")
        if not self._queue:
            return b""
        return (self._queue.pop(0) + "\n").encode("utf-8")

    def close(self) -> None:
        return None


def open_serial(device: str, baud: int, timeout: float = 0.2) -> object:
    import serial

    return serial.Serial(device, baudrate=baud, timeout=timeout, write_timeout=1.0)


def candidate_bauds(preferred: int | None) -> tuple[int, ...]:
    if preferred is None:
        return _BAUDS
    return (preferred,)
