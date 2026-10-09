"""Espera de un movimiento, tomada de la secuencia del canal en el archivo."""

from __future__ import annotations


def sequence_wait(bench, axis_id: str) -> float:
    channel = next(item for item in bench.channels if item.id == axis_id)
    return max(move.espera_fin_s for move in bench.secuencias[channel.secuencia])


def move_timeout(distance_mm: float, feed_mm_min: float, consulta_s: float, espera_fin_s: float) -> float:
    travel_s = 0.0 if feed_mm_min <= 0 else abs(distance_mm) / feed_mm_min * 60.0
    return max(consulta_s, espera_fin_s, travel_s + consulta_s)
