"""Qué hace la sesión con la respuesta de la placa."""

from __future__ import annotations

from tonf.manual.drivers import apply_reports, parse_m114, parse_m122
from tonf.manual.frame import to_logical
from tonf.manual.model import AXES, Pending, accepted, num, rejected, within
from tonf.manual.steps import mm_per_step
from tonf.manual.status import motor_lines


def ingest(console, call, body: str) -> tuple[list[str], bool]:
    if call.effect == "m122":
        if rejected(body) or not accepted(body):
            return [f"RECHAZADO la placa no aceptó {call.command}."], True
        reports, ambiguous = parse_m122(body)
        apply_reports(console, reports, ambiguous)
        lines = motor_lines(console)
        if ambiguous:
            lines.append(
                "AVISO M122 marcó "
                + ", ".join(ambiguous)
                + " sin columna de eje. Esa línea no bloquea un motor; revise el texto."
            )
        return lines, False
    if call.effect == "m115":
        lowered = body.lower()
        console.identity_ok = accepted(body) and (
            "firmware_name" in lowered or "marlin" in lowered or "ok" in lowered
        )
        if not console.identity_ok:
            return ["RECHAZADO la placa no se identificó como Marlin."], True
        return [], False
    if rejected(body) or not accepted(body):
        if console.pending is not None:
            console.axes[console.pending.axis].uncertain = True
            console.pending = None
        return [f"RECHAZADO la placa no aceptó {call.command}."], True
    if call.effect == "current":
        if call.axis in console.axes:
            console.axes[call.axis].current_set = True
        return [], False
    if call.effect == "ref":
        state = console.axes[call.axis]
        state.position_mm = call.target_mm
        state.referenced = True
        state.uncertain = False
        return [f"OK referencia {call.axis} en {num(call.target_mm or 0)} mm. El carro tiene que estar libre ahí."], False
    if call.effect == "arm":
        console.pending = Pending(call.axis, call.target_mm or 0.0, call.kind, call.contact_mm)
        return [], False
    if call.effect == "confirm":
        return _confirm(console, body), False
    if call.effect == "pos":
        return _read_pos(console, body), False
    return [], False


def _confirm(console, body: str) -> list[str]:
    pending = console.pending
    console.pending = None
    if pending is None:
        return ["AVISO llegó M114 sin un movimiento pendiente."]
    state = console.axes[pending.axis]
    reported = parse_m114(body).get(state.letra)
    logical = None if reported is None else to_logical(reported, state.signo)
    seen = pending.target_mm if logical is None else logical
    if logical is not None and abs(logical - pending.target_mm) > mm_per_step(state.pasos_por_mm):
        state.position_mm = logical
        state.uncertain = True
        return [
            f"AVISO {pending.axis}: se pidió {num(pending.target_mm)} mm y M114 dice {num(logical or 0)} mm.",
            "RECHAZADO la posición queda incierta. Mande POS. Si el carro está contra el metal, suelte y apártelo a mano.",
        ]
    state.position_mm = seen
    state.uncertain = False
    if pending.kind == "tope-min":
        state.mechanical_min = pending.contact_mm
        state.soft_min = pending.target_mm
    elif pending.kind == "tope-max":
        state.mechanical_max = pending.contact_mm
        state.soft_max = pending.target_mm
    lines = [f"OK {pending.axis} ahora en {num(seen)} mm."]
    if pending.kind == "tope-min":
        lines.append(
            f"OK tope mínimo de {pending.axis} en {num(pending.contact_mm or 0)} mm. "
            f"Límite de trabajo {num(pending.target_mm)} mm."
        )
    elif pending.kind == "tope-max":
        lines.append(
            f"OK tope máximo de {pending.axis} en {num(pending.contact_mm or 0)} mm. "
            f"Límite de trabajo {num(pending.target_mm)} mm."
        )
    if state.mechanical_min is not None and state.mechanical_max is not None:
        if state.soft_min is not None and state.soft_max is not None and state.soft_min < state.soft_max:
            length = state.soft_max - state.soft_min
            state.confirmed_without_probe = False
            lines.append(
                f"OK riel de {pending.axis}: {num(state.soft_min)}…{num(state.soft_max)} mm, "
                f"longitud {num(length)} mm."
            )
    return lines


def _read_pos(console, body: str) -> list[str]:
    found = parse_m114(body)
    lines = []
    for axis_id in AXES:
        state = console.axes[axis_id]
        if not state.referenced:
            continue
        marlin = found.get(state.letra)
        seen = None if marlin is None else to_logical(marlin, state.signo)
        if seen is None:
            state.uncertain = True
            lines.append(f"RECHAZADO POS no trajo {state.letra}. {axis_id} sigue incierto.")
            continue
        state.position_mm = seen
        if state.soft_min is not None and state.soft_max is not None and not within(seen, state.soft_min, state.soft_max):
            state.uncertain = True
            lines.append(
                f"RECHAZADO {axis_id} está en {num(seen)} mm, fuera de "
                f"{num(state.soft_min)}…{num(state.soft_max)} mm. "
                "Suelte, aparte el carro a mano, ANULAR y referencie de nuevo."
            )
            continue
        state.uncertain = False
        lines.append(f"OK {axis_id} en {num(seen)} mm según M114.")
    if not lines:
        lines.append("OK M114 leído. Ningún eje tiene referencia.")
    return lines
