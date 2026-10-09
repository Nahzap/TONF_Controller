"""Lee el tope en M119 y la carga StallGuard en M122.

En el TMC2209 el pin DIAG solo se activa en stealthChop, y Marlin además
deja ese camino apagado fuera de un G28. Por eso un M119 durante un G1
puede seguir en open con el carro ya contra el metal. La carga útil está
en sg_result. Con el eje en marcha, tstep trae un tiempo de paso; al
terminar el G1 vuelve a max. Una carga baja en ese reposo es el fin de
la orden, no el metal. sg_result 0 también es reposo.
"""

from __future__ import annotations

import re

from tonf.parse import parse_m119

_ORDER = ("X", "Y", "Z", "E0", "E1")


def axis_stalled(body: str, axis: str) -> bool | None:
    found = parse_m119(body.splitlines())
    names = {f"{axis.lower()}_min", f"{axis.lower()}_max"}
    values = [found[name] for name in found if name.lower() in names]
    if not values:
        return None
    return any(value.lower() == "triggered" for value in values)


def espera_entre_muestras(feed: float, paso_mm: float | None, travel_s: float) -> float:
    """Sin paso, la carga se lee seguido. Con paso, el eje corre ese tramo antes de cada lectura.

    El tramo es el que ya movió el husillo sin interrogar al driver en medio.
    """
    if paso_mm is None or feed <= 0:
        return 0.02
    return min(paso_mm / feed * 60.0, max(travel_s, 0.02))


def frena_si_sigue_en_marcha(caida: Caida, sg: int | None, moving: bool | None) -> bool:
    """El reposo al terminar la orden no es el tope. tstep en max deja moving en False."""
    if moving is False:
        return False
    return caida.toma(sg)


def stalled_load(sg: int | None, umbral: int) -> bool:
    """True si la carga está entre 1 y el umbral. El 0 es el reposo, no el tope."""
    return sg is not None and 0 < sg < umbral


class Caida:
    """Tope si la carga baja del umbral, o si cae frente al pico de esa misma marcha."""

    def __init__(self, umbral: int, fraccion: float, muestras: int, piso: int | None = None) -> None:
        self.umbral = umbral
        self.fraccion = fraccion
        self.muestras = muestras
        self.piso = umbral if piso is None else piso
        self.pico = 0
        self.seguidas = 0

    def toma(self, sg: int | None) -> bool:
        if sg is None or sg <= 0:
            return False
        if sg > self.pico:
            self.pico = sg
            self.seguidas = 0
        if self.pico < self.piso:
            return False
        if sg < self.umbral:
            return True
        if sg < self.pico * self.fraccion:
            self.seguidas += 1
            return self.seguidas >= self.muestras
        self.seguidas = 0
        return False


def load_sample(body: str, axis: str) -> tuple[int | None, bool | None]:
    """sg_result del eje, y si tstep lo muestra en marcha.

    moving es False en reposo (tstep max), True si hay un tiempo de paso,
    None si el M122 no trajo la fila.
    """
    sg_text = _cell(body, "sg_result", axis)
    step_text = _cell(body, "tstep", axis)
    sg = int(sg_text) if sg_text is not None and sg_text.isdigit() else None
    if step_text is None:
        return sg, None
    token = step_text.strip().lower()
    if token == "max":
        return sg, False
    return sg, bool(re.fullmatch(r"\d+", token))


def _cell(body: str, label: str, axis: str) -> str | None:
    if axis not in _ORDER:
        return None
    index = _ORDER.index(axis)
    prefix = label.lower()
    for raw in body.splitlines():
        text = raw.strip()
        if not text.lower().startswith(prefix):
            continue
        parts = [part for part in re.split(r"\t+|\s{2,}", text) if part]
        if not parts or parts[0].lower() != prefix:
            continue
        values = parts[1:]
        if index < len(values):
            return values[index]
    return None
