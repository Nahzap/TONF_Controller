"""Mínimo, máximo y longitud útil de un eje."""

from __future__ import annotations

from tonf.manual.axis_cmd import geometry_reason
from tonf.manual.grammar import axis_name
from tonf.manual.model import EPS, Plan, num, parse_float, within


def plan_margen(console, rest: list[str]) -> Plan:
    if len(rest) != 1:
        return Plan(["RECHAZADO MARGEN pide un número en mm."])
    mm = parse_float(rest[0])
    if mm is None or mm <= 0:
        return Plan(["RECHAZADO el margen tiene que ser mayor que 0."])
    console.margin_mm = mm
    return Plan([f"OK margen de tope {num(mm)} mm. Al marcar TOPE el eje retrocede esa distancia."])


def plan_lim(console, rest: list[str]) -> Plan:
    confirmar = False
    tokens = list(rest)
    if tokens and tokens[-1].upper() == "CONFIRMAR":
        confirmar = True
        tokens.pop()
    if len(tokens) != 3:
        return Plan(["RECHAZADO LIM pide eje, mínimo y máximo. Ejemplo: LIM X 20 280 CONFIRMAR"])
    axis = axis_name(tokens[0])
    low = parse_float(tokens[1])
    high = parse_float(tokens[2])
    if axis is None or low is None or high is None:
        return Plan(["RECHAZADO LIM pide eje, mínimo y máximo. Ejemplo: LIM X 20 280 CONFIRMAR"])
    reason = geometry_reason(console, axis)
    if reason:
        return Plan([f"RECHAZADO {reason}"])
    state = console.axes[axis]
    assert state.compiled_min is not None and state.compiled_max is not None
    assert state.position_mm is not None
    if low >= high:
        return Plan(["RECHAZADO el mínimo tiene que ser menor que el máximo."])
    if not within(low, state.compiled_min, state.compiled_max) or not within(high, state.compiled_min, state.compiled_max):
        return Plan([
            f"RECHAZADO el tramo tiene que entrar en la caja compilada "
            f"{num(state.compiled_min)}…{num(state.compiled_max)} mm."
        ])
    if not within(state.position_mm, low, high):
        return Plan([
            f"RECHAZADO la posición {num(state.position_mm)} mm quedaría fuera de {num(low)}…{num(high)} mm."
        ])
    identified = state.mechanical_min is not None and state.mechanical_max is not None
    if identified:
        assert state.soft_min is not None and state.soft_max is not None
        if low < state.soft_min - EPS or high > state.soft_max + EPS:
            return Plan([
                "RECHAZADO LIM solo puede achicar el tramo ya marcado. "
                f"Ahora es {num(state.soft_min)}…{num(state.soft_max)} mm."
            ])
        state.soft_min = low
        state.soft_max = high
        state.proposed = None
        length = high - low
        return Plan([f"OK {axis} limitado a {num(low)}…{num(high)} mm, longitud {num(length)} mm."])
    if not confirmar:
        state.proposed = (low, high)
        return Plan([
            f"AVISO propuesta de {axis}: {num(low)}…{num(high)} mm. M sigue bloqueado.",
            "Marque el metal con P y TOPE MIN / TOPE MAX, o repita la orden con CONFIRMAR.",
        ])
    state.soft_min = low
    state.soft_max = high
    state.proposed = None
    state.confirmed_without_probe = True
    length = high - low
    return Plan([
        f"OK {axis} limitado a {num(low)}…{num(high)} mm, longitud {num(length)} mm.",
        f"AVISO esos topes no se midieron en el riel. Cada M queda cortado a {num(console.bench.sin_topes_mm)} mm "
        "hasta TOPE MIN y TOPE MAX.",
    ])
