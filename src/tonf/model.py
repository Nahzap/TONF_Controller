"""Resultado de un indicador del banco."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Indicator:
    id: str
    titulo: str
    estado: str
    valor: str
    detalle: str
    limitante: str = ""


@dataclass
class Suite:
    indicators: list[Indicator] = field(default_factory=list)
    transcript: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
