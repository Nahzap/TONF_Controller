"""Lectura de respuestas de Marlin y grbl, sin interpretar movimiento."""

from __future__ import annotations

import math
import re
from typing import Iterable

_M115_KEYS = (
    "SOURCE_CODE_URL",
    "PROTOCOL_VERSION",
    "MACHINE_TYPE",
    "EXTRUDER_COUNT",
    "UUID",
)

_HALT_MARKERS = ("printer halted", "mintemp", "maxtemp", "kill() called")


def is_terminator(line: str) -> bool:
    head = line.strip().lower()
    return head == "ok" or head.startswith("ok ") or head.startswith("error")


def looks_like_marlin(lines: Iterable[str]) -> bool:
    for line in lines:
        lowered = line.lower()
        if "firmware_name:" in lowered or lowered.startswith("echo:") or lowered == "start":
            return True
    return False


def looks_like_grbl(lines: Iterable[str]) -> bool:
    blob = "\n".join(lines).lower()
    return "grbl" in blob or "[ver:" in blob


def looks_halted(lines: Iterable[str]) -> bool:
    blob = "\n".join(lines).lower()
    return any(marker in blob for marker in _HALT_MARKERS)


def parse_m115(lines: Iterable[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    caps: list[str] = []
    for line in lines:
        if line.startswith("Cap:"):
            caps.append(line.removeprefix("Cap:").strip())
            continue
        if "FIRMWARE_NAME:" not in line:
            continue
        remainder = line.split("FIRMWARE_NAME:", 1)[1]
        cuts = []
        for key in _M115_KEYS:
            idx = remainder.find(f" {key}:")
            if idx != -1:
                cuts.append((idx, key))
        cuts.sort()
        if not cuts:
            fields["FIRMWARE_NAME"] = remainder.strip()
            continue
        fields["FIRMWARE_NAME"] = remainder[: cuts[0][0]].strip()
        for i, (idx, key) in enumerate(cuts):
            start = idx + len(key) + 2
            end = cuts[i + 1][0] if i + 1 < len(cuts) else len(remainder)
            fields[key] = remainder[start:end].strip()
    if caps:
        fields["CAPACIDADES"] = ", ".join(caps)
    return fields


_ENDSTOP = re.compile(r"^([A-Za-z0-9_]+):\s*(\S+)\s*$")


def parse_m119(lines: Iterable[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in lines:
        match = _ENDSTOP.match(line.strip())
        if match and match.group(1).lower() not in {"ok", "echo"}:
            found[match.group(1)] = match.group(2)
    return found


_GRBL_BANNER = re.compile(r"(GrblHAL|grblHAL|Grbl)\s+([0-9]+(?:\.[0-9]+)*[a-z]?)")


def parse_grbl_banner(lines: Iterable[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        match = _GRBL_BANNER.search(line)
        if match:
            fields["FIRMWARE"] = match.group(1)
            fields["VERSION"] = match.group(2)
        if line.startswith("[VER:"):
            fields["VER"] = line.strip("[]")
        if line.startswith("[OPT:"):
            fields["OPT"] = line.strip("[]")
    return fields


def percentile(samples: list[float], fraction: float) -> float:
    if not samples:
        raise ValueError("sin muestras")
    ordered = sorted(samples)
    rank = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[min(len(ordered) - 1, rank)]


def printable(text: str, limit: int = 180) -> str:
    cleaned = "".join(char if char.isprintable() else "." for char in text)
    if len(cleaned) > limit:
        return cleaned[: limit - 3] + "..."
    return cleaned
