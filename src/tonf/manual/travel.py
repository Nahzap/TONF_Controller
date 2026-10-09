"""Sonda, tope mecánico y la orden M. Traduce pasos a un G1 absoluto o lo rechaza."""

from __future__ import annotations

from tonf.manual.axis_cmd import geometry_reason
from tonf.manual.grammar import parse_motion_args, tope_args
from tonf.manual.frame import to_marlin
from tonf.manual.model import EPS, Axis, Call, Plan, num
from tonf.manual.pace import move_timeout, sequence_wait
from tonf.manual.steps import steps_to_mm
from tonf.manual.window import rejection_if_outside, rejection_if_probe_too_long, rejection_if_unmarked_too_long


def locked_calls(letra: str, herramienta: int | None, pause: float) -> list[Call]:
    """Mantiene el eje tomado: sin DIAG de reposo y sin apagado por inactividad."""
    if letra == "E":
        blind = f"M914 T{herramienta} E0"
    else:
        blind = f"M914 {letra}0"
    return [
        Call(blind, pause),
        Call("M84 S0", pause),
        Call("M17", pause),
    ]


def plan_apagar(console, quit: bool) -> Plan:
    """Baja el eje asignado al mínimo y después suelta la corriente."""
    pause = console.bench.consulta_s
    axis_id = console.selected
    state = console.axes.get(axis_id) if axis_id else None
    if state is None or not state.referenced or state.mechanical_min is None:
        text = "OK motores sueltos. Menú cerrado." if quit else "RECHAZADO no hay un mínimo al que volver."
        return Plan([text], [Call("M18", pause)], quit=quit)
    target = state.mechanical_min
    feed = console.bench.avance_mm_min
    distance = abs((state.position_mm if state.position_mm is not None else target) - target)
    timeout = move_timeout(distance, feed, pause, sequence_wait(console.bench, state.axis_id))
    return Plan(
        [f"APAGADO {state.axis_id}: vuelve al mínimo {num(target)} mm y después se suelta."],
        [
            Call("G90", pause),
            Call(
                f"G1 {state.letra}{num(to_marlin(target, state.signo))} F{num(feed)}",
                timeout,
            ),
            Call("M400", timeout),
            Call("M18", pause),
        ],
        quit=quit,
    )


def current_calls(console, state: Axis) -> list[Call]:
    if state.current_set:
        return []
    pause = console.bench.consulta_s
    bit = 1 if state.sigilo else 0
    if state.letra == "E":
        current = f"M906 T{state.herramienta} E{state.m906_ma or state.corriente_ma}"
        chopper = f"M569 T{state.herramienta} E S{bit}"
        stall = f"M914 T{state.herramienta} E{state.sensibilidad_stall}"
    else:
        current = f"M906 {state.letra}{state.m906_ma or state.corriente_ma}"
        chopper = f"M569 {state.letra} S{bit}"
        stall = f"M914 {state.letra}{state.sensibilidad_stall}"
    return [
        Call(current, pause),
        Call(chopper, pause),
        Call(stall, pause, "current", state.axis_id),
    ]


def travel_calls(console, state: Axis, target: float, feed: float, kind: str, contact: float | None) -> list[Call]:
    mm = abs(target - (state.position_mm or target))
    timeout = move_timeout(mm, feed, console.bench.consulta_s, sequence_wait(console.bench, state.axis_id))
    calls = current_calls(console, state)
    calls.append(Call("G90", console.bench.consulta_s))
    calls.append(
        Call(
            f"G1 {state.letra}{num(to_marlin(target, state.signo))} F{num(feed)}",
            timeout,
            "arm",
            state.axis_id,
            target,
            contact,
            kind,
        )
    )
    calls.append(Call("M400", timeout))
    calls.append(Call("M114", console.bench.consulta_s, "confirm"))
    others = [name for name in ("X", "Y", "Z", "E") if name != state.letra]
    calls.append(Call("M18 " + " ".join(others), console.bench.consulta_s))
    return calls


def plan_tope(console, rest: list[str]) -> Plan:
    axis, which, error = tope_args(rest, console.selected)
    if error:
        return Plan([f"RECHAZADO {error}"])
    assert axis is not None and which is not None
    reason = geometry_reason(console, axis)
    if reason:
        return Plan([f"RECHAZADO {reason}"])
    state = console.axes[axis]
    assert state.position_mm is not None
    assert state.compiled_min is not None and state.compiled_max is not None
    contact = state.position_mm
    if which == "MIN":
        soft = contact + console.margin_mm
        if soft >= state.compiled_max - EPS:
            return Plan(["RECHAZADO no hay sitio para retroceder el margen dentro de la caja compilada."])
        if state.soft_max is not None and soft >= state.soft_max - EPS:
            return Plan(["RECHAZADO el mínimo, con el margen, no queda por debajo del máximo."])
        kind = "tope-min"
    else:
        soft = contact - console.margin_mm
        if soft <= state.compiled_min + EPS:
            return Plan(["RECHAZADO no hay sitio para retroceder el margen dentro de la caja compilada."])
        if state.soft_min is not None and soft <= state.soft_min + EPS:
            return Plan(["RECHAZADO el máximo, con el margen, no queda por encima del mínimo."])
        kind = "tope-max"
    feed, feed_error = accepted_feed(console, state, None)
    if feed_error or feed is None:
        return Plan([f"RECHAZADO {feed_error}"])
    console.selected = axis
    return Plan([], travel_calls(console, state, soft, feed, kind, contact))


def plan_motion(console, rest: list[str], probe: bool) -> Plan:
    axis_name, steps, feed, error = parse_motion_args(rest, allow_feed=not probe)
    if error:
        return Plan([f"RECHAZADO {error}"])
    assert steps is not None
    axis = axis_name or console.selected
    if axis is None:
        return Plan(["RECHAZADO falta el eje. USAR X, o escriba el eje en la orden."])
    reason = geometry_reason(console, axis)
    if reason:
        return Plan([f"RECHAZADO {reason}"])
    state = console.axes[axis]
    assert state.position_mm is not None
    assert state.compiled_min is not None and state.compiled_max is not None
    if probe:
        too_long = rejection_if_probe_too_long(steps, state.pasos_por_mm, console.bench.sonda_mm)
        if too_long:
            return Plan([f"RECHAZADO {too_long}"])
    mm = steps_to_mm(steps, state.pasos_por_mm)
    target = state.position_mm + mm
    if probe:
        low = state.compiled_min if state.soft_min is None else max(state.compiled_min, state.soft_min)
        high = state.compiled_max if state.soft_max is None else min(state.compiled_max, state.soft_max)
    else:
        if state.soft_min is None or state.soft_max is None:
            return Plan([
                f"RECHAZADO {axis} no tiene mínimo y máximo. "
                "Márquelo con TOPE MIN y TOPE MAX, o use LIM con CONFIRMAR."
            ])
        low, high = state.soft_min, state.soft_max
    outside = rejection_if_outside(state.position_mm, target, low, high, state.pasos_por_mm)
    if outside:
        return Plan([f"RECHAZADO {outside}"])
    topes = state.mechanical_min is not None and state.mechanical_max is not None
    if not probe and state.confirmed_without_probe and not topes:
        unmarked = rejection_if_unmarked_too_long(steps, state.pasos_por_mm, axis, console.bench.sin_topes_mm)
        if unmarked:
            return Plan([f"RECHAZADO {unmarked}"])
    chosen, feed_error = accepted_feed(console, state, None if probe else feed)
    if feed_error or chosen is None:
        return Plan([f"RECHAZADO {feed_error}"])
    console.selected = axis
    return Plan([], travel_calls(console, state, target, chosen, "move", None))


def accepted_feed(console, state: Axis, requested: float | None) -> tuple[float | None, str | None]:
    feed = console.bench.avance_mm_min if requested is None else requested
    ceiling = console.bench.avances_mm_s[state.letra] * 60.0
    if feed <= EPS or feed > ceiling + EPS:
        return None, (
            f"el avance de {state.axis_id} tiene que ser mayor que 0 "
            f"y no pasar {num(ceiling)} mm/min, que es el M203 del archivo."
        )
    return feed, None
