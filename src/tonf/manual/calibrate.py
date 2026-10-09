"""Autocalibración desde el mínimo físico.

Se aplica corriente y un paso hacia arriba. Si ese paso atasca, el sentido
es el contrario. El atasco siguiente, ya con el eje en movimiento, es el máximo.
Desde ahí se retrocede al punto medio y el motor queda habilitado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tonf.manual.model import Axis, Call, Plan, num
from tonf.manual.travel import locked_calls
from tonf.manual.pace import move_timeout
from tonf.manual.steps import legal_steps
from tonf.manual.store import Record


@dataclass
class Sample:
    ok: bool
    stalled: bool | None


@dataclass
class Calibrator:
    axis: str
    letra: str
    herramienta: int | None
    pasos_por_mm: float
    corriente_ma: int
    m906_ma: int
    sigilo: bool
    umbral_stall: int
    margin_mm: float
    span_max_mm: float
    pause_s: float
    step_mm: float
    feed: float
    espera_fin_s: float
    signo: int
    flipped: bool = False
    phase: str = "baseline"
    physical: float = 0.0
    pending: float = 0.0
    mechanical_max: float | None = None
    error: str = ""

    @classmethod
    def create(
        cls,
        state: Axis,
        pause_s: float,
        span_max_mm: float,
        margin_mm: float,
        step_mm: float,
        feed_mm_min: float,
        espera_fin_s: float,
    ) -> Calibrator:
        return cls(
            axis=state.axis_id,
            letra=state.letra,
            herramienta=state.herramienta,
            pasos_por_mm=state.pasos_por_mm,
            corriente_ma=state.corriente_ma,
            m906_ma=state.m906_ma,
            sigilo=state.sigilo,
            umbral_stall=state.sensibilidad_stall,
            margin_mm=margin_mm,
            span_max_mm=span_max_mm,
            pause_s=pause_s,
            step_mm=step_mm,
            feed=feed_mm_min,
            espera_fin_s=espera_fin_s,
            signo=state.signo,
        )

    def begin(self) -> Plan:
        self.phase = "baseline"
        pause = self.pause_s
        return Plan(
            [
                f"Autocalibración de {self.axis}. El carro está en el mínimo.",
                f"Paso {num(self.step_mm)} mm a {num(self.feed)} mm/min, sentido de prueba {self.signo:+d}.",
                "Se aplica corriente y se prueba si sube.",
                "La búsqueda queda en stealthChop: el TMC2209 no afirma el DIAG en spreadCycle.",
            ],
            [
                *_driver(self, spread=False),
                Call("G90", pause),
                Call(f"G92 {self.letra}0", pause),
                Call("M119", pause),
            ],
        )

    def advance(self, sample: Sample) -> Plan:
        if not sample.ok:
            return self._fail("La placa rechazó el tramo.")
        if sample.stalled is None:
            return self._fail("M119 no informó el final de este eje.")
        if self.phase == "baseline":
            if sample.stalled:
                return self._fail("El final ya está activo. No se mueve el eje.")
            self.phase = "step"
            self.pending = self.step_mm
            return self._absolute(self.pending, "Corriente aplicada. Primer paso para ver si sube.")
        if self.phase == "leave":
            if sample.stalled:
                return self._fail("Tampoco sube en el sentido contrario. No se sigue.")
            self.physical = self.pending
            return self._next_step(
                f"No subía. El sentido quedó en {self.signo:+d}. "
                f"{_desde_cero(self)}"
            )
        if self.phase == "backoff":
            if sample.stalled:
                return self._fail("No se pudo despegar del máximo.")
            assert self.mechanical_max is not None
            self.physical = self.mechanical_max - self.margin_mm
            self.phase = "mid"
            self.pending = self.mechanical_max / 2.0
            return self._absolute(self.pending, f"Máximo en {num(self.mechanical_max)} mm. Se va al punto medio.")
        if self.phase == "mid":
            if sample.stalled:
                return self._fail("Atasco yendo al punto medio.")
            self.physical = self.pending
            return self._done()
        if self.phase != "step":
            return self._fail("La rutina quedó en un estado que no puede seguir.")
        if sample.stalled and self.physical <= 1e-9 and not self.flipped:
            self.flipped = True
            self.signo = -self.signo
            self.phase = "leave"
            self.pending = self.step_mm
            return Plan(
                ["Ese sentido no sube. Se invierte y se busca el máximo."],
                [
                    Call("M410", self.pause_s),
                    Call("M17", self.pause_s),
                    Call("G90", self.pause_s),
                    Call(f"G92 {self.letra}0", self.pause_s),
                    *self._move_calls(self.pending),
                ],
            )
        if sample.stalled:
            return self._at_max()
        self.physical = self.pending
        return self._next_step(_desde_cero(self))

    def to_record(self, fecha: str | None = None) -> Record:
        if self.mechanical_max is None:
            raise RuntimeError("no hay máximo")
        length = self.mechanical_max
        low = self.margin_mm
        high = length - self.margin_mm
        mid = length / 2.0
        return Record(
            eje=self.axis,
            fecha=fecha or datetime.now().astimezone().isoformat(timespec="seconds"),
            pasos_por_mm=self.pasos_por_mm,
            sentido=self.signo,
            corriente_ma=self.corriente_ma,
            margen_mm=self.margin_mm,
            minimo_mecanico_mm=0.0,
            maximo_mecanico_mm=length,
            minimo_trabajo_mm=low,
            maximo_trabajo_mm=high,
            longitud_mm=length,
            punto_medio_mm=mid,
            pasos_entre_topes=legal_steps(length, self.pasos_por_mm),
            umbral_stall=self.umbral_stall,
            bloqueado=True,
        )

    def _next_step(self, message: str) -> Plan:
        nxt = self.physical + self.step_mm
        if nxt > self.span_max_mm + 1e-9:
            return self._fail(
                "No apareció el máximo dentro del recorrido permitido. Se detuvo para no seguir empujando."
            )
        self.pending = nxt
        self.phase = "step"
        return self._absolute(nxt, message)

    def _at_max(self) -> Plan:
        self.mechanical_max = self.physical
        if self.mechanical_max <= self.margin_mm * 2:
            return self._fail("El recorrido medido no deja sitio para el margen en los dos extremos.")
        self.phase = "backoff"
        free = self.mechanical_max - self.margin_mm
        retreat = self.margin_mm + self.step_mm
        back = self.signo * -retreat
        timeout = self._timeout(retreat)
        pasos = legal_steps(self.mechanical_max, self.pasos_por_mm)
        return Plan(
            [
                f"Tope máximo a {num(self.mechanical_max)} mm, {pasos} pasos desde 0. "
                "Se frena, se sostiene la corriente y se retrocede el margen."
            ],
            [
                Call("M410", self.pause_s),
                Call("M17", self.pause_s),
                Call("G91", self.pause_s),
                Call(f"G1 {self.letra}{num(back)} F{num(self.feed)}", timeout),
                Call("M400", timeout),
                Call("G90", self.pause_s),
                Call(f"G92 {self.letra}{num(self.signo * free)}", self.pause_s),
                Call("M119", self.pause_s),
            ],
        )

    def _done(self) -> Plan:
        self.phase = "done"
        bit = 1 if self.sigilo else 0
        chopper = _chopper(self, bit)
        mid = self.mechanical_max / 2.0 if self.mechanical_max is not None else self.physical
        return Plan(
            [
                f"OK {self.axis} calibrado: 0…{num(self.mechanical_max or 0)} mm, "
                f"punto medio {num(mid)} mm, sentido {self.signo:+d}.",
                "El eje queda bloqueado en el punto medio.",
                "Una carga no lo suelta: el DIAG de reposo queda en 0 y la placa no lo apaga por inactividad.",
            ],
            [Call(chopper, self.pause_s), *locked_calls(self.letra, self.herramienta, self.pause_s)],
        )

    def _fail(self, text: str) -> Plan:
        self.phase = "fail"
        self.error = text
        return Plan(
            [f"RECHAZADO {text}", "La corriente sigue aplicada para que el eje no caiga."],
            [Call("M410", self.pause_s), Call("M17", self.pause_s)],
        )

    def _absolute(self, physical: float, message: str) -> Plan:
        return Plan([message], [Call("G90", self.pause_s), *self._move_calls(physical)])

    def _move_calls(self, physical: float) -> list[Call]:
        timeout = self._timeout(self.step_mm)
        marlin = self.signo * physical
        return [
            Call(f"G1 {self.letra}{num(marlin)} F{num(self.feed)}", timeout),
        ]

    def _timeout(self, mm: float) -> float:
        return move_timeout(mm, self.feed, self.pause_s, self.espera_fin_s)


def _desde_cero(cal: Calibrator) -> str:
    pasos = legal_steps(cal.physical, cal.pasos_por_mm)
    return f"{cal.axis} en {num(cal.physical)} mm, {pasos} pasos desde 0."


def _driver(cal: Calibrator, spread: bool) -> list[Call]:
    pause = cal.pause_s
    bit = 0 if spread else (1 if cal.sigilo else 0)
    return [
        Call(_current(cal), pause),
        Call(_chopper(cal, bit), pause),
        Call(_stall(cal), pause),
    ]


def _current(cal: Calibrator) -> str:
    ma = cal.m906_ma or cal.corriente_ma
    if cal.letra == "E":
        return f"M906 T{cal.herramienta} E{ma}"
    return f"M906 {cal.letra}{ma}"


def _chopper(cal: Calibrator, bit: int) -> str:
    if cal.letra == "E":
        return f"M569 T{cal.herramienta} E S{bit}"
    return f"M569 {cal.letra} S{bit}"


def _stall(cal: Calibrator) -> str:
    if cal.letra == "E":
        return f"M914 T{cal.herramienta} E{cal.umbral_stall}"
    return f"M914 {cal.letra}{cal.umbral_stall}"
