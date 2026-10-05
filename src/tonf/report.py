"""Informe markdown de una pasada del banco."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tonf.model import Suite


def render(suite: Suite, when: datetime) -> str:
    stamp = when.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# Indicadores SKR V1.4 Turbo — {stamp}",
        "",
        "Sesión de solo lectura. No se envió movimiento ni se activó ningún MOSFET.",
        "",
        "| Indicador | Estado | Valor |",
        "| --- | --- | --- |",
    ]
    for item in suite.indicators:
        valor = item.valor.replace("|", "/")
        lines.append(f"| {item.titulo} | {item.estado} | {valor} |")
    lines.extend(["", "## Detalle", ""])
    for item in suite.indicators:
        lines.append(f"### {item.titulo}")
        lines.append("")
        lines.append(item.detalle)
        if item.limitante:
            lines.append("")
            lines.append(f"Limitante: {item.limitante}")
        lines.append("")
    if suite.notes:
        lines.extend(["## Notas", ""])
        lines.extend(f"- {note}" for note in suite.notes)
        lines.append("")
    if suite.transcript:
        lines.extend(["## Transcripción", "", "```text"])
        lines.extend(suite.transcript[:120])
        if len(suite.transcript) > 120:
            lines.append(f"... {len(suite.transcript) - 120} líneas más")
        lines.extend(["```", ""])
    return "\n".join(lines)


def write_report(suite: Suite, directory: Path, when: datetime | None = None) -> Path:
    moment = when or datetime.now()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{moment.strftime('%Y-%m-%d_%H%M%S')}_indicadores-skr.md"
    path.write_text(render(suite, moment), encoding="utf-8")
    return path
