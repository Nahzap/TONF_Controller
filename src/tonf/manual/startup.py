"""Ajuste de Marlin al abrir el menú. No incluye G0, G1 ni G28."""

from __future__ import annotations

from tonf.banco import Bench
from tonf.manual.model import Call, Plan, num


def startup_plan(bench: Bench) -> Plan:
    cold = "M302 S0" if bench.extrusion_en_frio else f"M302 S{bench.extrusion_min_c}"
    filament = "M412 S1" if bench.sensor_filamento else "M412 S0"
    feeds = " ".join(f"{axis}{num(bench.avances_mm_s[axis])}" for axis in ("X", "Y", "Z", "E"))
    values: dict[str, float] = {}
    for channel in bench.channels:
        values[channel.letra] = channel.pasos_por_mm
    steps = " ".join(f"{axis}{num(values[axis])}" for axis in ("X", "Y", "Z", "E") if axis in values)
    pause = bench.consulta_s
    return Plan(
        [],
        [
            Call("M115", pause, "m115"),
            Call(cold, pause),
            Call(filament, pause),
            Call(f"M203 {feeds}", pause),
            Call(f"M92 {steps}", pause),
            Call("G90", pause),
            Call("M122", bench.driver_s, "m122"),
        ],
    )
