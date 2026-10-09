"""Reconocimiento de drivers TMC2209 a partir de M122 y de M114."""

from __future__ import annotations

import re
from dataclasses import dataclass

from tonf.manual.model import AXES

_M122_NAME = {"X": "X", "Y": "Y", "Z": "Z", "E": "E0", "E0": "E0", "E1": "E1"}
_FAULTS = {
    "ola": "ola",
    "olb": "olb",
    "s2ga": "short",
    "s2gb": "short",
    "s2vsa": "short",
    "s2vsb": "short",
    "ot": "ot",
}
_COLUMNS = {"X": 1, "Y": 2, "Z": 3, "E0": 4, "E1": 5}
_CONN = re.compile(r"Testing\s+([A-Za-z0-9]+)\s+connection\.\.\.\s*(.+)", re.IGNORECASE)
_M114 = re.compile(r"([XYZE]):\s*([-+]?\d+(?:\.\d+)?)")


@dataclass
class DriverReport:
    uart_ok: bool
    detail: str
    ola: bool = False
    olb: bool = False
    short: bool = False
    ot: bool = False


def parse_m114(body: str) -> dict[str, float]:
    for line in body.splitlines():
        head = line.split("Count", 1)[0]
        found = {match.group(1): float(match.group(2)) for match in _M114.finditer(head)}
        if found:
            return found
    return {}


def parse_m122(body: str) -> tuple[dict[str, DriverReport], list[str]]:
    """Devuelve un informe por eje y los nombres de falla que no traían columna."""
    reports = {axis: DriverReport(False, "no apareció en M122") for axis in AXES}
    ambiguous: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line == "ok" or line.startswith("ok "):
            continue
        match = _CONN.search(line)
        if match:
            axis = _M122_NAME.get(match.group(1).upper())
            if axis is None:
                continue
            detail = match.group(2).strip()
            previous = reports[axis]
            reports[axis] = DriverReport(
                detail.upper().startswith("OK"),
                "OK" if detail.upper().startswith("OK") else detail,
                previous.ola,
                previous.olb,
                previous.short,
                previous.ot,
            )
            continue
        flag = _flag_name(line)
        if flag is None:
            continue
        kind = _FAULTS[flag]
        cells = raw.split("\t")
        mapped = len(cells) > 1
        if mapped:
            for axis, index in _COLUMNS.items():
                if index < len(cells) and _marked(cells[index]):
                    _set_fault(reports, axis, kind)
        else:
            parts = line.split(None, 1)
            rest = parts[1] if len(parts) > 1 else ""
            if "*" in rest or rest.strip().lower() in {"1", "true"}:
                ambiguous.append(flag)
    return reports, ambiguous


def apply_reports(console, reports: dict[str, DriverReport], ambiguous: list[str] | None = None) -> None:
    console.ambiguous_faults = list(ambiguous or [])
    for axis, report in reports.items():
        state = console.axes[axis]
        state.uart_ok = report.uart_ok
        state.uart_detail = report.detail
        state.ola = report.ola
        state.olb = report.olb
        state.short = report.short
        state.ot = report.ot


def _flag_name(line: str) -> str | None:
    parts = line.strip().split()
    if not parts:
        return None
    name = parts[0].lower()
    if name == "otpw":
        return None
    return name if name in _FAULTS else None


def _marked(cell: str) -> bool:
    text = cell.strip().lower()
    return text not in {"", "0", "false", "no"}


def _set_fault(reports: dict[str, DriverReport], axis: str, kind: str) -> None:
    report = reports[axis]
    if kind == "ola":
        report.ola = True
    elif kind == "olb":
        report.olb = True
    elif kind == "short":
        report.short = True
    elif kind == "ot":
        report.ot = True
