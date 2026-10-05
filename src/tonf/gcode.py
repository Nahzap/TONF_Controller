"""Envío de G-code a grblHAL.

El protocolo es el de grbl: una línea, esperar `ok` o `error`.
La limpieza de comentarios es la que el propio controlador ya entiende
(paréntesis y punto y coma). No hay otro dialecto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tonf.link import Link

_PARENS = re.compile(r"\([^)]*\)")


@dataclass
class StreamResult:
    sent: list[str] = field(default_factory=list)
    ok: int = 0
    stopped: str = ""


def normalize_line(line: str) -> str:
    without_semicolon = line.split(";", 1)[0]
    without_comments = _PARENS.sub("", without_semicolon)
    return " ".join(without_comments.split()).upper()


def lines_from_text(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = normalize_line(raw)
        if not line or line == "%":
            continue
        lines.append(line)
    return lines


def load_gcode(path: Path) -> list[str]:
    return lines_from_text(path.read_text(encoding="utf-8", errors="replace"))


def stream_lines(link: Link, lines: list[str], timeout: float = 120.0) -> StreamResult:
    result = StreamResult()
    for line in lines:
        exchange = link.exchange(line, timeout=timeout)
        result.sent.append(line)
        if exchange.timed_out:
            result.stopped = f"Sin respuesta a: {line}"
            return result
        reply = exchange.lines[-1]
        if reply.lower().startswith("error"):
            result.stopped = f"{line} -> {reply}"
            return result
        result.ok += 1
    return result


def stream_program(link: Link, lines: list[str], comprobar: bool, timeout: float = 120.0) -> StreamResult:
    if not comprobar:
        return stream_lines(link, lines, timeout)
    entered = link.exchange("$C", timeout=2.0)
    if entered.timed_out or (entered.lines and entered.lines[-1].lower().startswith("error")):
        reply = entered.lines[-1] if entered.lines else "sin respuesta"
        return StreamResult(stopped=f"No se pudo activar el modo comprobación ($C): {reply}")
    try:
        return stream_lines(link, lines, timeout)
    finally:
        link.exchange("$C", timeout=2.0)
