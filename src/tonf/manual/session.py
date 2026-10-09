"""Estado de la sesión y despacho de una línea del protocolo."""

from __future__ import annotations

from tonf.banco import Bench, corriente_m906
from tonf.manual.axis_cmd import mark_uncertain as flag_uncertain, plan_anular, plan_forzar, plan_permitir, plan_usar
from tonf.manual.drivers import DriverReport, apply_reports
from tonf.manual.grammar import help_lines
from tonf.manual.limits_cmd import plan_lim, plan_margen
from tonf.manual.model import Axis, Call, Plan
from tonf.manual.origin import plan_pos, plan_ref
from tonf.manual.reply import ingest
from tonf.manual.startup import startup_plan
from tonf.manual.status import banner_lines, status_lines
from tonf.manual.travel import plan_apagar, plan_motion, plan_tope


class MenuSession:
    def __init__(self, bench: Bench) -> None:
        self.bench = bench
        self.selected: str | None = None
        self.margin_mm = bench.margen_mm
        self.identity_ok = False
        self.pending = None
        self.ambiguous_faults: list[str] = []
        self.axes: dict[str, Axis] = {}
        for channel in bench.ordered():
            low: float | None = None
            high: float | None = None
            if channel.id in bench.limites_mm:
                low, high = bench.limites_mm[channel.id]
            self.axes[channel.id] = Axis(
                axis_id=channel.id,
                letra=channel.letra,
                herramienta=channel.herramienta,
                pasos_por_mm=channel.pasos_por_mm,
                corriente_ma=channel.corriente_ma,
                m906_ma=corriente_m906(channel),
                sigilo=channel.sigilo,
                sensibilidad_stall=channel.sensibilidad_stall,
                compiled_min=low,
                compiled_max=high,
                permitted=channel.id == "X",
                sentido_config=channel.sentido,
                signo=channel.sentido,
            )

    def startup_plan(self) -> Plan:
        return startup_plan(self.bench)

    def note_drivers(self, reports: dict[str, DriverReport], ambiguous: list[str] | None = None) -> None:
        apply_reports(self, reports, ambiguous)

    def plan(self, line: str) -> Plan:
        self.pending = None
        tokens = line.strip().split()
        if not tokens:
            return Plan()
        head = tokens[0].upper()
        rest = tokens[1:]
        if head in {"?", "AYUDA"}:
            return Plan(help_lines(self))
        if head == "ID":
            return Plan([], [Call("M122", self.bench.driver_s, "m122")])
        if head == "ESTADO":
            return Plan(status_lines(self))
        if head == "USAR":
            return plan_usar(self, rest)
        if head == "PERMITIR":
            return plan_permitir(self, rest, True)
        if head == "BLOQUEAR":
            return plan_permitir(self, rest, False)
        if head == "FORZAR":
            return plan_forzar(self, rest)
        if head == "REF":
            return plan_ref(self, rest)
        if head == "P":
            return plan_motion(self, rest, True)
        if head == "TOPE":
            return plan_tope(self, rest)
        if head == "MARGEN":
            return plan_margen(self, rest)
        if head == "LIM":
            return plan_lim(self, rest)
        if head == "M":
            return plan_motion(self, rest, False)
        if head == "POS":
            return plan_pos(self, rest)
        if head == "ANULAR":
            return plan_anular(self, rest)
        if head == "PARAR":
            flag_uncertain(self)
            pause = self.bench.consulta_s
            return Plan(
                ["OK paro rápido. Motores sueltos. La posición queda por confirmar con POS."],
                [Call("M410", pause, "plain"), Call("M18", pause, "plain")],
            )
        if head == "SOLTAR":
            flag_uncertain(self)
            return Plan(
                [
                    "OK motores sueltos.",
                    "AVISO si movió un eje a mano, M114 no lo ve. ANULAR y vuelva a dar REF.",
                ],
                [Call("M18", self.bench.consulta_s, "plain")],
            )
        if head in {"APAGAR", "CERRAR"}:
            return plan_apagar(self, quit=True)
        return Plan(["RECHAZADO orden desconocida. Escriba ?"])

    def apply(self, plan: Plan, bodies: list[str] | None = None) -> list[str]:
        replies = list(plan.replies)
        for index, call in enumerate(plan.calls):
            body = "ok" if bodies is None else bodies[index]
            extra, halt = self.ingest(call, body)
            replies.extend(extra)
            if halt:
                break
        return replies

    def ingest(self, call: Call, body: str) -> tuple[list[str], bool]:
        return ingest(self, call, body)

    def banner_lines(self) -> list[str]:
        return banner_lines(self)

    def mark_uncertain(self) -> None:
        flag_uncertain(self)
