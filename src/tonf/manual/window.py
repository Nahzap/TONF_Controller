"""Rechazo de un destino que saldría del mínimo o del máximo."""

from __future__ import annotations

from tonf.manual.model import num, within
from tonf.manual.steps import legal_steps, steps_to_mm


def rejection_if_outside(
    position_mm: float,
    target_mm: float,
    low: float,
    high: float,
    pasos_por_mm: float,
) -> str | None:
    if within(target_mm, low, high):
        return None
    bound = high if target_mm > high else low
    room = legal_steps(bound - position_mm, pasos_por_mm)
    edge = "máximo" if target_mm > high else "mínimo"
    return (
        f"el destino {num(target_mm)} mm pasa el {edge} {num(bound)} mm. "
        f"En este sentido caben {room} pasos. No se envió el movimiento."
    )


def rejection_if_probe_too_long(steps: int, pasos_por_mm: float, sonda_mm: float) -> str | None:
    mm = abs(steps_to_mm(steps, pasos_por_mm))
    if mm <= sonda_mm + 1e-6:
        return None
    cap = legal_steps(sonda_mm, pasos_por_mm)
    return (
        f"la sonda admite como máximo {cap} pasos ({num(sonda_mm)} mm) por orden. "
        "Así se puede frenar antes del metal."
    )


def rejection_if_unmarked_too_long(steps: int, pasos_por_mm: float, axis: str, sin_topes_mm: float) -> str | None:
    mm = abs(steps_to_mm(steps, pasos_por_mm))
    if mm <= sin_topes_mm + 1e-6:
        return None
    cap_steps = legal_steps(sin_topes_mm, pasos_por_mm)
    return (
        f"sin los dos topes mecánicos cada M se corta a {num(sin_topes_mm)} mm "
        f"({cap_steps} pasos en {axis}). Esta orden pide {num(mm)} mm."
    )
