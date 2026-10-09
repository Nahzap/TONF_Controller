"""Permiso, reconocimiento y borrado de un eje. No arma un G1."""

from __future__ import annotations

from tonf.manual.grammar import one_axis
from tonf.manual.model import Axis, Call, Plan
from tonf.manual.store import remove_record


def block_reason(console, axis: str) -> str | None:
    if axis not in console.axes:
        return f"no existe el eje {axis}."
    state = console.axes[axis]
    if state.compiled_min is None or state.compiled_max is None:
        return f"{axis} no tiene riel en limites_mm. Este menú no lo mueve."
    if not state.permitted:
        return f"{axis} está bloqueado. Solo X arranca permitido. PERMITIR {axis} cuando el motor esté conectado."
    if state.uart_ok is None:
        return f"falta ID. {axis} todavía no fue reconocido."
    if not state.uart_ok:
        return f"{axis} no contestó por UART ({state.uart_detail}). No se mueve."
    if state.short or state.ot:
        return f"{axis} tiene cortocircuito o sobretemperatura. No se mueve."
    if (state.ola or state.olb) and not state.forced:
        marks = []
        if state.ola:
            marks.append("ola")
        if state.olb:
            marks.append("olb")
        return (
            f"{axis} marca carga abierta ({', '.join(marks)}). "
            f"Revise el plug. FORZAR {axis} lo ignora solo en esta sesión."
        )
    return None


def geometry_reason(console, axis: str) -> str | None:
    reason = block_reason(console, axis)
    if reason:
        return reason
    state = console.axes[axis]
    if not state.referenced or state.position_mm is None:
        return f"{axis} no tiene referencia. Ponga el carro en un punto libre y mande REF {axis} y los mm."
    if state.uncertain:
        return (
            f"la posición de {axis} no es confiable. Mande POS. "
            "Si el carro quedó contra el metal, suelte, apártelo a mano y ANULAR."
        )
    return None


def plan_usar(console, rest: list[str]) -> Plan:
    axis, error = one_axis(rest)
    if error:
        return Plan([f"RECHAZADO {error}"])
    assert axis is not None
    reason = block_reason(console, axis)
    if reason:
        return Plan([f"RECHAZADO {reason}"])
    console.selected = axis
    return Plan([f"OK eje {axis} seleccionado."])


def plan_permitir(console, rest: list[str], permit: bool) -> Plan:
    axis, error = one_axis(rest)
    if error:
        return Plan([f"RECHAZADO {error}"])
    assert axis is not None
    state = console.axes[axis]
    if state.compiled_min is None:
        return Plan([f"RECHAZADO {axis} no tiene riel en limites_mm. Este menú no lo mueve."])
    state.permitted = permit
    if not permit and console.selected == axis:
        console.selected = None
    if permit:
        return Plan([f"OK {axis} permitido. Hacen falta ID, REF y límites antes de M."])
    return Plan([f"OK {axis} bloqueado. No se enviarán pasos a ese motor."])


def plan_forzar(console, rest: list[str]) -> Plan:
    axis, error = one_axis(rest)
    if error:
        return Plan([f"RECHAZADO {error}"])
    assert axis is not None
    state = console.axes[axis]
    if state.compiled_min is None:
        return Plan([f"RECHAZADO {axis} no tiene riel. FORZAR no lo habilita."])
    if state.uart_ok is not True:
        return Plan([f"RECHAZADO FORZAR no inventa el driver de {axis}. Hace falta ID con uart OK."])
    if state.short or state.ot:
        return Plan(["RECHAZADO FORZAR no salta un cortocircuito ni una sobretemperatura."])
    state.forced = True
    return Plan([
        f"AVISO {axis}: en esta sesión se ignora la carga abierta.",
        f"OK {axis} forzado.",
    ])


def plan_anular(console, rest: list[str]) -> Plan:
    axis, error = one_axis(rest)
    if error:
        return Plan([f"RECHAZADO {error}"])
    assert axis is not None
    clear_geometry(console.axes[axis])
    if console.selected == axis:
        console.selected = None
    removed = remove_record(console.bench.path, axis)
    note = " Se borró el json de calibración." if removed else ""
    return Plan(
        [f"OK {axis} sin referencia y sin límites. El motor se suelta.{note}"],
        [Call("M18", console.bench.consulta_s)],
    )


def mark_uncertain(console) -> None:
    for state in console.axes.values():
        if state.referenced:
            state.uncertain = True


def clear_geometry(state: Axis) -> None:
    state.signo = state.sentido_config
    state.position_mm = None
    state.referenced = False
    state.uncertain = False
    state.soft_min = None
    state.soft_max = None
    state.mechanical_min = None
    state.mechanical_max = None
    state.confirmed_without_probe = False
    state.proposed = None
