"""Pasa de milímetros del riel a la coordenada que entiende Marlin.

El cero del riel es el mínimo físico. `signo` +1 hace subir a Marlin en positivo.
`signo` -1 hace subir a Marlin en negativo.
"""

from __future__ import annotations


def to_marlin(riel_mm: float, signo: int) -> float:
    return signo * riel_mm


def to_logical(marlin_mm: float, signo: int) -> float:
    return signo * marlin_mm
