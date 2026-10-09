"""Lectura de una línea del protocolo. No decide si el eje puede moverse."""

from __future__ import annotations

import re

from tonf.manual.model import AXES, num, parse_float

_STEPS = re.compile(r"[+-]?\d+")


def help_lines(console) -> list[str]:
    bench = console.bench
    return [
        "Menú TONF. Una orden por línea. El host habla con Marlin; estas órdenes no son G-code.",
        "Paso, avance, margen, sonda y tope sin medición salen de [calibracion] en el archivo.",
        "Al abrir: eje, corriente máxima mA, inicio mm y fin mm. Ejemplo: X 800 0 300.",
        "El punto medio es la mitad de ese tramo. X! repite la rutina con esos números.",
        "Solo X arranca permitido. Y y Z se habilitan si se eligen. E0 y E1 no tienen riel.",
        "M no sale si el destino pasa el mínimo o el máximo: ese paso no se envía.",
        "ID                         reconoce los cinco drivers (M122).",
        "ESTADO                     posición, límites y longitud útil.",
        "USAR X                     selecciona el eje.",
        "PERMITIR Y                 habilita otro eje con riel. BLOQUEAR Y lo quita.",
        "REF X 150                  declara la posición lógica actual, en mm. No mueve el motor.",
        f"P X -80                    sonda: como máximo {num(bench.sonda_mm)} mm por orden.",
        "TOPE MIN                   marca el extremo y retrocede el margen. TOPE MAX el otro.",
        f"MARGEN {num(bench.margen_mm)}                   el archivo trae ese margen. La orden lo cambia en esta sesión.",
        "LIM X 20 280               propone el mínimo y el máximo. M sigue bloqueado.",
        "LIM X 20 280 CONFIRMAR     acepta ese tramo sin haber marcado los dos topes.",
        f"M X 800                    mueve +800 pasos. Sin F usa {num(bench.avance_mm_min)} mm/min del archivo.",
        "M 80                       igual, sobre el eje seleccionado.",
        "POS                        lee M114. ANULAR X borra referencia, límites y el json.",
        "PARAR                      M410 y suelta motores. SOLTAR suelta sin frenar un movimiento.",
        "FORZAR X                   ignora carga abierta de ese eje en esta sesión.",
        "APAGAR                     el eje asignado vuelve al mínimo y después se suelta.",
        "CERRAR                     igual que APAGAR, y sale. ? repite este texto.",
    ]


def axis_name(token: str) -> str | None:
    name = token.upper()
    if name in AXES:
        return name
    return None


def one_axis(rest: list[str]) -> tuple[str | None, str | None]:
    if len(rest) != 1:
        return None, "la orden pide un eje: X, Y o Z."
    axis = axis_name(rest[0])
    if axis is None:
        return None, "eje desconocido. Use X, Y, Z, E0 o E1."
    return axis, None


def tope_args(rest: list[str], selected: str | None) -> tuple[str | None, str | None, str | None]:
    tokens = [token.upper() for token in rest]
    axis: str | None = None
    which: str | None = None
    if len(tokens) == 1 and tokens[0] in {"MIN", "MAX"}:
        which = tokens[0]
        axis = selected
    elif len(tokens) == 2 and tokens[1] in {"MIN", "MAX"}:
        axis = axis_name(tokens[0])
        which = tokens[1]
        if axis is None:
            return None, None, "eje desconocido. Ejemplo: TOPE X MIN"
    else:
        return None, None, "TOPE pide MIN o MAX. Ejemplo: TOPE X MIN"
    if axis is None:
        return None, None, "falta el eje. USAR X, o escriba TOPE X MIN."
    return axis, which, None


def parse_motion_args(
    rest: list[str], allow_feed: bool
) -> tuple[str | None, int | None, float | None, str | None]:
    tokens = list(rest)
    axis = None
    if tokens and axis_name(tokens[0]):
        axis = axis_name(tokens.pop(0))
    if not tokens:
        return axis, None, None, "faltan los pasos. Ejemplo: M X 800"
    if not _STEPS.fullmatch(tokens[0]):
        return axis, None, None, "los pasos tienen que ser un entero distinto de cero."
    steps = int(tokens.pop(0))
    if steps == 0:
        return axis, None, None, "los pasos no pueden ser 0."
    if not tokens:
        return axis, steps, None, None
    if not allow_feed:
        return axis, None, None, "la sonda no acepta avance."
    feed, error = _parse_feed(tokens)
    if error:
        return axis, None, None, error
    return axis, steps, feed, None


def _parse_feed(tokens: list[str]) -> tuple[float | None, str | None]:
    if len(tokens) == 1 and tokens[0].upper().startswith("F") and len(tokens[0]) > 1:
        value = parse_float(tokens[0][1:])
    elif len(tokens) == 2 and tokens[0].upper() == "F":
        value = parse_float(tokens[1])
    else:
        return None, "el avance se escribe F y el número, junto o separado."
    if value is None:
        return None, "el avance no es un número."
    return value, None
