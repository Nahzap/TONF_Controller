"""Texto de estado. No abre el puerto."""

from __future__ import annotations

from tonf.manual.model import AXES, num
from tonf.manual.steps import legal_steps


def motor_lines(console) -> list[str]:
    lines = []
    for axis_id in AXES:
        state = console.axes[axis_id]
        if state.uart_ok is None:
            uart = "sin ID"
        elif state.uart_ok:
            uart = "OK"
        else:
            uart = state.uart_detail
        faults = []
        if state.ola:
            faults.append("ola")
        if state.olb:
            faults.append("olb")
        if state.short:
            faults.append("cortocircuito")
        if state.ot:
            faults.append("sobretemperatura")
        fault = ", ".join(faults) if faults else "ninguna"
        lines.append(
            f"MOTOR {axis_id} uart={uart} permitido={'sí' if state.permitted else 'no'} "
            f"fallas={fault} pasos/mm={num(state.pasos_por_mm)}"
        )
    return lines


def status_lines(console) -> list[str]:
    lines = [
        f"Selección: {console.selected or 'ninguna'}",
        f"Margen de tope: {num(console.margin_mm)} mm",
        *motor_lines(console),
    ]
    for axis_id in AXES:
        state = console.axes[axis_id]
        if state.compiled_min is None or state.compiled_max is None:
            lines.append(f"  {axis_id}: sin riel en limites_mm. Este menú no lo mueve.")
            continue
        if state.referenced and state.position_mm is not None:
            mark = "  posición incierta" if state.uncertain else ""
            lines.append(f"  {axis_id}: posición {num(state.position_mm)} mm{mark}")
        else:
            lines.append(f"  {axis_id}: sin referencia")
        if state.soft_min is not None and state.soft_max is not None:
            length = state.soft_max - state.soft_min
            lines.append(
                f"  {axis_id}: límites {num(state.soft_min)}…{num(state.soft_max)} mm, "
                f"longitud {num(length)} mm, {legal_steps(length, state.pasos_por_mm)} pasos"
            )
        elif state.proposed is not None:
            low, high = state.proposed
            lines.append(f"  {axis_id}: propuesta {num(low)}…{num(high)} mm, M bloqueado")
        else:
            lines.append(
                f"  {axis_id}: sin límites de trabajo. "
                f"Caja compilada {num(state.compiled_min)}…{num(state.compiled_max)} mm, no es el metal."
            )
        if state.mechanical_min is not None:
            lines.append(f"  {axis_id}: tope mecánico mínimo {num(state.mechanical_min)} mm")
        if state.mechanical_max is not None:
            lines.append(f"  {axis_id}: tope mecánico máximo {num(state.mechanical_max)} mm")
        if state.mechanical_min is not None and state.mechanical_max is not None:
            lines.append(f"  {axis_id}: sentido {state.signo:+d}")
    return lines


def banner_lines(console) -> list[str]:
    return [
        "Al iniciar: eje, corriente máxima mA, inicio mm y fin mm. Ejemplo: X 800 0 300.",
        "El punto medio es la mitad entre ese inicio y ese fin. Si ya hay json, X solo lo usa.",
        "Escriba ? para ver las órdenes.",
        *motor_lines(console),
    ]
