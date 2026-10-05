"""Comandos permitidos en el banco.

La primera sesión no mueve motores ni enciende MOSFET. Cualquier otra
cadena se rechaza antes de llegar al puerto.
"""

from __future__ import annotations

ALLOWED = frozenset({"M115", "M114", "M119", "$I", "$$", "?"})


class UnsafeCommand(ValueError):
    """El comando saldría del conjunto de solo lectura."""


def guard(command: str) -> str:
    text = command.strip()
    if text not in ALLOWED:
        raise UnsafeCommand(
            f"Comando no permitido en este banco: {text!r}. "
            f"Solo lectura: {', '.join(sorted(ALLOWED))}."
        )
    return text
