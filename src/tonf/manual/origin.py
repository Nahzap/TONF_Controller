"""Referencia lógica del eje. G92 no mueve el motor."""

from __future__ import annotations

from tonf.manual.axis_cmd import block_reason
from tonf.manual.grammar import axis_name
from tonf.manual.frame import to_marlin
from tonf.manual.model import Call, Plan, num, parse_float, within
from tonf.manual.travel import current_calls


def plan_ref(console, rest: list[str]) -> Plan:
    if len(rest) != 2:
        return Plan(["RECHAZADO REF pide el eje y los mm. Ejemplo: REF X 150"])
    axis = axis_name(rest[0])
    mm = parse_float(rest[1])
    if axis is None or mm is None:
        return Plan(["RECHAZADO REF pide el eje y los mm. Ejemplo: REF X 150"])
    reason = block_reason(console, axis)
    if reason:
        return Plan([f"RECHAZADO {reason}"])
    state = console.axes[axis]
    if state.soft_min is not None or state.soft_max is not None or state.mechanical_min is not None or state.mechanical_max is not None:
        return Plan([f"RECHAZADO {axis} ya tiene límites. ANULAR {axis} antes de otra referencia."])
    assert state.compiled_min is not None and state.compiled_max is not None
    if not within(mm, state.compiled_min, state.compiled_max):
        return Plan([
            f"RECHAZADO {axis} no acepta una referencia en {num(mm)} mm. "
            f"La caja compilada es {num(state.compiled_min)}…{num(state.compiled_max)} mm."
        ])
    console.selected = axis
    pause = console.bench.consulta_s
    calls = current_calls(console, state)
    calls.append(Call("G90", pause))
    calls.append(Call(f"G92 {state.letra}{num(to_marlin(mm, state.signo))}", pause, "ref", axis, mm))
    return Plan([], calls)


def plan_pos(console, _rest: list[str]) -> Plan:
    if not any(state.referenced for state in console.axes.values()):
        return Plan(["RECHAZADO no hay un eje referenciado. POS no tiene contra qué comparar."])
    return Plan([], [Call("M114", console.bench.consulta_s, "pos")])
