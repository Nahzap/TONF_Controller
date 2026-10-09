"""Tipos del menú manual. No habla con la placa."""

from __future__ import annotations

from dataclasses import dataclass, field

AXES = ("X", "Y", "Z", "E0", "E1")
EPS = 1e-6


@dataclass
class Call:
    command: str
    timeout_s: float
    effect: str = "plain"
    axis: str = ""
    target_mm: float | None = None
    contact_mm: float | None = None
    kind: str = ""


@dataclass
class Plan:
    replies: list[str] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    quit: bool = False


@dataclass
class Pending:
    axis: str
    target_mm: float
    kind: str
    contact_mm: float | None = None


@dataclass
class Axis:
    axis_id: str
    letra: str
    herramienta: int | None
    pasos_por_mm: float
    corriente_ma: int
    m906_ma: int
    sigilo: bool
    sensibilidad_stall: int
    compiled_min: float | None
    compiled_max: float | None
    permitted: bool = False
    uart_ok: bool | None = None
    uart_detail: str = "sin ID"
    ola: bool = False
    olb: bool = False
    short: bool = False
    ot: bool = False
    forced: bool = False
    sentido_config: int = 1
    signo: int = 1
    position_mm: float | None = None
    referenced: bool = False
    uncertain: bool = False
    soft_min: float | None = None
    soft_max: float | None = None
    mechanical_min: float | None = None
    mechanical_max: float | None = None
    confirmed_without_probe: bool = False
    current_set: bool = False
    proposed: tuple[float, float] | None = None


def num(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def within(value: float, low: float, high: float) -> bool:
    return low - EPS <= value <= high + EPS


def accepted(text: str) -> bool:
    return any(line == "ok" or line.startswith("ok ") for line in text.splitlines())


def rejected(body: str) -> bool:
    lowered = body.lower()
    if "unknown command" in lowered or "cold extrusion" in lowered or "invalid extruder" in lowered:
        return True
    return any(line.startswith("Error") for line in body.splitlines())


def parse_float(token: str) -> float | None:
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None
