"""Espera de un movimiento, tomada de la secuencia del canal en el archivo."""

from __future__ import annotations


def sequence_wait(bench, axis_id: str) -> float:
    channel = next(item for item in bench.channels if item.id == axis_id)
    return max(move.espera_fin_s for move in bench.secuencias[channel.secuencia])


def tramos_mm(distancia_mm: float, paso_mm: float) -> list[float]:
    """Parte el regreso en los tramos que ya movieron el husillo, conservando el signo."""
    if paso_mm <= 0:
        raise ValueError("el paso tiene que ser mayor que 0")
    signo = 1.0 if distancia_mm >= 0 else -1.0
    restante = abs(distancia_mm)
    tramos: list[float] = []
    while restante > 1e-9:
        tramo = min(paso_mm, restante)
        tramos.append(signo * tramo)
        restante -= tramo
    return tramos


def move_timeout(distance_mm: float, feed_mm_min: float, consulta_s: float, espera_fin_s: float) -> float:
    travel_s = 0.0 if feed_mm_min <= 0 else abs(distance_mm) / feed_mm_min * 60.0
    return max(consulta_s, espera_fin_s, travel_s + consulta_s)
