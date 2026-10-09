"""Json de calibración, uno por eje, junto a config/banco.toml."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Record:
    eje: str
    fecha: str
    pasos_por_mm: float
    sentido: int
    corriente_ma: int
    margen_mm: float
    minimo_mecanico_mm: float
    maximo_mecanico_mm: float
    minimo_trabajo_mm: float
    maximo_trabajo_mm: float
    longitud_mm: float
    punto_medio_mm: float
    pasos_entre_topes: int
    umbral_stall: int
    bloqueado: bool

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Record:
        if data.get("eje") not in {"X", "Y", "Z"}:
            raise ValueError("eje")
        if int(data["sentido"]) not in {1, -1}:
            raise ValueError("sentido")
        record = cls(
            eje=str(data["eje"]),
            fecha=str(data["fecha"]),
            pasos_por_mm=float(data["pasos_por_mm"]),
            sentido=int(data["sentido"]),
            corriente_ma=int(data["corriente_ma"]),
            margen_mm=float(data["margen_mm"]),
            minimo_mecanico_mm=float(data["minimo_mecanico_mm"]),
            maximo_mecanico_mm=float(data["maximo_mecanico_mm"]),
            minimo_trabajo_mm=float(data["minimo_trabajo_mm"]),
            maximo_trabajo_mm=float(data["maximo_trabajo_mm"]),
            longitud_mm=float(data["longitud_mm"]),
            punto_medio_mm=float(data["punto_medio_mm"]),
            pasos_entre_topes=int(data["pasos_entre_topes"]),
            umbral_stall=int(data["umbral_stall"]),
            bloqueado=bool(data.get("bloqueado", True)),
        )
        if record.minimo_trabajo_mm >= record.maximo_trabajo_mm:
            raise ValueError("tramo")
        if record.punto_medio_mm < record.minimo_trabajo_mm or record.punto_medio_mm > record.maximo_trabajo_mm:
            raise ValueError("medio")
        return record


def record_path(config_file: Path, eje: str) -> Path:
    return config_file.parent / "calibracion" / f"{eje}.json"


def load_record(path: Path) -> Record | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return Record.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_record(path: Path, record: Record) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def remove_record(config_file: Path, eje: str) -> bool:
    path = record_path(config_file, eje)
    if not path.is_file():
        return False
    path.unlink()
    return True
