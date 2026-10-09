"""Conversión entre pasos del planificador y milímetros."""

from __future__ import annotations

import math


def mm_per_step(pasos_por_mm: float) -> float:
    return 1.0 / pasos_por_mm


def steps_to_mm(steps: int, pasos_por_mm: float) -> float:
    return steps / pasos_por_mm


def legal_steps(delta_mm: float, pasos_por_mm: float) -> int:
    """Pasos enteros que no pasan de delta_mm."""
    raw = delta_mm * pasos_por_mm
    if raw >= 0:
        return int(math.floor(raw + 1e-9))
    return int(math.ceil(raw - 1e-9))
