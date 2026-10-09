"""Envío por el puerto. No decide límites: solo ejecuta un plan ya aceptado."""

from __future__ import annotations

from dataclasses import dataclass

from tonf.banco import Bench
from tonf.manual.model import Plan
from tonf.manual.session import MenuSession

_FORBIDDEN = frozenset({"G28", "G0", "M104", "M109", "M140", "M190"})


@dataclass
class Run:
    replies: list[str]
    last_body: str
    halted: bool


def execute_detail(session: MenuSession, plan: Plan, send) -> Run:
    replies = list(plan.replies)
    last_body = ""
    for call in plan.calls:
        head = call.command.split()[0].upper()
        if head in _FORBIDDEN or call.command.upper().startswith("M211 S0"):
            replies.append(f"RECHAZADO el menú no envía {call.command}.")
            return Run(replies, last_body, True)
        try:
            body = send(call.command, call.timeout_s)
        except KeyboardInterrupt:
            send("M410", session.bench.consulta_s)
            send("M17", session.bench.consulta_s)
            session.mark_uncertain()
            replies.append("OK interrumpido. Se frenó el eje y la corriente sigue aplicada.")
            return Run(replies, last_body, True)
        last_body = body if isinstance(body, str) else str(body)
        extra, halt = session.ingest(call, last_body)
        replies.extend(extra)
        if halt:
            if call.command != "M18":
                send("M17", session.bench.consulta_s)
                replies.append("La corriente sigue aplicada.")
            return Run(replies, last_body, True)
    return Run(replies, last_body, False)


def execute_plan(session: MenuSession, plan: Plan, send) -> list[str]:
    return execute_detail(session, plan, send).replies


def serve(session: MenuSession, send, read, write) -> int:
    try:
        for line in execute_plan(session, session.startup_plan(), send):
            write(line)
        if not session.identity_ok:
            return 1
        for line in session.banner_lines():
            write(line)
        from tonf.manual.boot import prepare

        ready = prepare(session, send, read, write)
        if ready is not None:
            return ready
        while True:
            try:
                line = read("tonf> ")
            except EOFError:
                line = "CERRAR"
            except KeyboardInterrupt:
                for item in execute_plan(session, session.plan("PARAR"), send):
                    write(item)
                return 0
            if line is None:
                line = "CERRAR"
            plan = session.plan(line)
            for item in execute_plan(session, plan, send):
                write(item)
            if plan.quit:
                return 0
    except KeyboardInterrupt:
        write("OK interrumpido.")
        return 0


def run_menu(bench: Bench) -> int:
    from tonf.banco import open_port, transact

    print(f"Menú en {bench.puerto} a {bench.baud} baudios.", flush=True)
    print(f"Abriendo {bench.puerto}. El puerto reinicia la placa.", flush=True)
    try:
        port = open_port(bench.puerto, bench.baud, bench.espera_apertura_s)
    except OSError as exc:
        print(f"No se pudo abrir {bench.puerto}: {exc}", flush=True)
        return 1

    def send(command: str, timeout: float) -> str:
        print(f"===== {command} =====", flush=True)
        return transact(port, command, timeout, 0.05)

    def vigilar(command: str, timeout: float, vigia) -> str:
        print(f"===== {command} =====", flush=True)
        return transact(port, command, timeout, 0.05, vigia)

    send.vigilar = vigilar
    send.puerto = port

    def write(text: str) -> None:
        print(text, flush=True)

    try:
        return serve(MenuSession(bench), send, input, write)
    finally:
        port.close()
