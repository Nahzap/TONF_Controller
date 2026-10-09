"""Pregunta el eje al abrir el monitor y carga o corre la calibración."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime

from tonf.banco import corriente_m906
from tonf.manual.calibrate import Calibrator, Sample
from tonf.manual.frame import to_marlin
from tonf.manual.model import Call, Plan, num
from tonf.manual.pace import move_timeout, sequence_wait
from tonf.manual.runner import execute_detail, execute_plan
from tonf.manual.stall import axis_stalled, load_sample, stalled_load
from tonf.manual.steps import legal_steps
from tonf.manual.store import Record, load_record, record_path, save_record
from tonf.manual.travel import current_calls, locked_calls

_RAIL = frozenset({"X", "Y", "Z"})


@dataclass(frozen=True)
class Choice:
    axis: str
    force: bool
    corriente_ma: int | None = None
    inicio_mm: float | None = None
    fin_mm: float | None = None

    @property
    def declared(self) -> bool:
        return self.corriente_ma is not None and self.inicio_mm is not None and self.fin_mm is not None


def ask_axis(read, write) -> Choice | None:
    while True:
        try:
            raw = read("Eje, corriente mA, inicio mm y fin mm (X 800 0 300). CERRAR sale. X! repite: ")
        except EOFError:
            return None
        if raw is None:
            return None
        text = raw.strip().upper().replace(",", ".")
        if not text:
            continue
        if text in {"CERRAR", "Q", "SALIR"}:
            return None
        parsed = _parse_choice(text)
        if isinstance(parsed, str):
            write(parsed)
            continue
        return parsed


def _parse_choice(text: str) -> Choice | str:
    parts = text.split()
    token = parts[0]
    force = token.endswith("!")
    name = token[:-1] if force else token
    if name not in _RAIL:
        return "RECHAZADO use X, Y o Z."
    if len(parts) == 1:
        return Choice(name, force)
    if len(parts) != 4:
        return "RECHAZADO indique eje, corriente mA, inicio mm y fin mm. Ejemplo: X 800 0 300"
    current = _int_token(parts[1])
    inicio = _float_token(parts[2])
    fin = _float_token(parts[3])
    if current is None or inicio is None or fin is None:
        return "RECHAZADO corriente, inicio y fin tienen que ser números. Ejemplo: X 800 0 300"
    if current < 1:
        return "RECHAZADO la corriente tiene que ser mayor que 0."
    if fin <= inicio:
        return "RECHAZADO el fin tiene que ser mayor que el inicio."
    return Choice(name, force, current, inicio, fin)


def _int_token(token: str) -> int | None:
    try:
        value = float(token)
    except ValueError:
        return None
    if abs(value - round(value)) > 1e-9:
        return None
    return int(round(value))


def _float_token(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None


def _refuse_choice(session, choice: Choice, write) -> bool | None:
    """None acepta la línea. False vuelve a preguntar. True cierra con error."""
    state = session.axes[choice.axis]
    if state.compiled_min is None or state.compiled_max is None:
        write(f"RECHAZADO {choice.axis} no tiene riel.")
        return True
    if state.uart_ok is not True:
        detail = "sin ID" if state.uart_ok is None else state.uart_detail
        write(f"RECHAZADO {choice.axis} no contestó por UART ({detail}).")
        return True
    if state.short or state.ot:
        write(f"RECHAZADO {choice.axis} tiene cortocircuito o sobretemperatura.")
        return True
    if (state.ola or state.olb) and not state.forced:
        write(f"RECHAZADO {choice.axis} marca carga abierta. Revise el plug antes de calibrar.")
        return True
    if not choice.declared:
        if choice.force:
            write("RECHAZADO X! pide corriente mA, inicio mm y fin mm. Ejemplo: X! 800 0 300")
            return False
        return None
    if choice.corriente_ma > session.bench.techo_ma:
        write(
            f"RECHAZADO la corriente {choice.corriente_ma} mA pasa el techo "
            f"{session.bench.techo_ma} mA."
        )
        return False
    length = choice.fin_mm - choice.inicio_mm
    if length <= session.bench.margen_mm * 2:
        write("RECHAZADO el tramo no deja sitio para el margen a los dos lados del punto medio.")
        return False
    return None


def hold_plan(session, record: Record) -> Plan:
    state = session.axes[record.eje]
    pause = session.bench.consulta_s
    calls = current_calls(session, state)
    calls.extend(
        (
            Call("G90", pause),
            Call(
                f"G92 {state.letra}{num(to_marlin(record.punto_medio_mm, record.sentido))}",
                pause,
                "ref",
                record.eje,
                record.punto_medio_mm,
            ),
            *locked_calls(state.letra, state.herramienta, pause),
        )
    )
    return Plan(
        [
            f"OK {record.eje} leído de calibración ({record.fecha}).",
            f"OK riel {num(record.minimo_mecanico_mm)}…{num(record.maximo_mecanico_mm)} mm, "
            f"punto medio {num(record.punto_medio_mm)} mm, "
            f"sentido {record.sentido:+d}.",
            "No se repite la rutina. El eje queda bloqueado en el punto medio.",
            "Una carga no lo suelta: el DIAG de reposo queda en 0 y la placa no lo apaga por inactividad.",
        ],
        calls,
    )


def install(session, record: Record) -> None:
    state = session.axes[record.eje]
    state.permitted = True
    state.signo = record.sentido
    state.position_mm = record.punto_medio_mm
    state.referenced = True
    state.uncertain = False
    state.mechanical_min = record.minimo_mecanico_mm
    state.mechanical_max = record.maximo_mecanico_mm
    state.soft_min = record.minimo_trabajo_mm
    state.soft_max = record.maximo_trabajo_mm
    state.confirmed_without_probe = False
    state.proposed = None
    state.current_set = True
    session.selected = record.eje
    session.margin_mm = record.margen_mm


def prepare(session, send, read, write) -> int | None:
    session.margin_mm = session.bench.margen_mm
    write("El carro tiene que estar en el mínimo físico. Ese punto es el inicio.")
    write("El punto medio es la mitad entre el inicio y el fin. No lo marca el atasco.")
    while True:
        choice = ask_axis(read, write)
        if choice is None:
            for line in execute_plan(session, session.plan("CERRAR"), send):
                write(line)
            return 0
        refused = _refuse_choice(session, choice, write)
        if refused is not None:
            if refused:
                return 1
            continue
        state = session.axes[choice.axis]
        state.permitted = True
        session.selected = choice.axis
        path = record_path(session.bench.path, choice.axis)
        if not choice.declared:
            existing = load_record(path)
            if existing is not None and abs(existing.pasos_por_mm - state.pasos_por_mm) > 1e-6:
                write("AVISO el json no coincide con los pasos/mm de ahora. Indique corriente, inicio y fin.")
                continue
            if existing is None:
                write("RECHAZADO indique corriente mA, inicio mm y fin mm. Ejemplo: X 800 0 300")
                continue
            return _finish_saved(session, existing, send, write)
        if choice.force and path.is_file():
            write(f"AVISO se repite la calibración de {choice.axis}.")
        record = _place_declared(session, choice, send, write)
        if record is None:
            return 1
        save_record(path, record)
        write(f"OK calibración guardada en {path}.")
        return _finish_saved(session, record, send, write)


def _finish_saved(session, record: Record, send, write) -> int | None:
    detail = execute_detail(session, hold_plan(session, record), send)
    for line in detail.replies:
        write(line)
    if detail.halted:
        return 1
    install(session, record)
    return None


def _place_declared(session, choice: Choice, send, write) -> Record | None:
    state = session.axes[choice.axis]
    channel = next(item for item in session.bench.channels if item.id == choice.axis)
    adjusted = replace(channel, corriente_ma=choice.corriente_ma)
    state.corriente_ma = choice.corriente_ma
    state.m906_ma = corriente_m906(adjusted)
    state.current_set = False
    inicio = choice.inicio_mm
    fin = choice.fin_mm
    medio = (inicio + fin) / 2.0
    margen = session.bench.margen_mm
    feed = session.bench.avance_mm_min
    pause = session.bench.consulta_s
    distance = medio - inicio
    timeout = move_timeout(distance, feed, pause, sequence_wait(session.bench, choice.axis))
    write(
        f"{choice.axis}: corriente {choice.corriente_ma} mA, "
        f"tramo {num(inicio)}…{num(fin)} mm, punto medio {num(medio)} mm."
    )
    plan = Plan(
        [f"Se va al punto medio {num(medio)} mm. El inicio queda en {num(inicio)} mm."],
        [
            *current_calls(session, state),
            Call("G90", pause),
            Call(f"G92 {state.letra}{num(to_marlin(inicio, state.signo))}", pause),
            Call(
                f"G1 {state.letra}{num(to_marlin(medio, state.signo))} F{num(feed)}",
                timeout,
            ),
        ],
    )
    detail = execute_detail(session, plan, send)
    stalled = False
    if not detail.halted:
        stalled = _watch_travel(session, state, distance, feed, send, write)
    for line in detail.replies:
        write(line)
    if detail.halted or stalled:
        write("RECHAZADO no llegó al punto medio declarado. La corriente sigue aplicada.")
        return None
    length = fin - inicio
    return Record(
        eje=choice.axis,
        fecha=datetime.now().astimezone().isoformat(timespec="seconds"),
        pasos_por_mm=state.pasos_por_mm,
        sentido=state.signo,
        corriente_ma=choice.corriente_ma,
        margen_mm=margen,
        minimo_mecanico_mm=inicio,
        maximo_mecanico_mm=fin,
        minimo_trabajo_mm=inicio + margen,
        maximo_trabajo_mm=fin - margen,
        longitud_mm=length,
        punto_medio_mm=medio,
        pasos_entre_topes=legal_steps(length, state.pasos_por_mm),
        umbral_stall=state.sensibilidad_stall,
        bloqueado=True,
    )


def _watch_travel(session, state, distance_mm: float, feed: float, send, write) -> bool:
    """True si el eje atasca antes de terminar el tramo. La corriente sigue."""
    travel = 0.0 if feed <= 0 else abs(distance_mm) / feed * 60.0
    deadline = time.monotonic() + travel + 0.25
    time.sleep(min(travel * 0.25, 0.2))
    while time.monotonic() < deadline:
        body = send("M122", session.bench.consulta_s)
        text = body if isinstance(body, str) else str(body)
        sg, _moving = load_sample(text, state.axis_id)
        if sg is not None:
            write(f"{state.axis_id} sg {sg}")
        if stalled_load(sg, state.sensibilidad_stall):
            send("M410", session.bench.consulta_s)
            send("M17", session.bench.consulta_s)
            write(
                f"StallGuard {state.axis_id} {sg} bajo {state.sensibilidad_stall}. "
                "Se frena y se sostiene la corriente."
            )
            return True
        time.sleep(0.02)
    body = send("M119", session.bench.consulta_s)
    text = body if isinstance(body, str) else str(body)
    stalled = axis_stalled(text, state.axis_id)
    if stalled:
        send("M410", session.bench.consulta_s)
        send("M17", session.bench.consulta_s)
        write(f"M119 {state.axis_id} TRIGGERED. Se frena y se sostiene la corriente.")
        return True
    send("M400", session.bench.consulta_s)
    return False


def _run(session, routine: Calibrator, send, write) -> bool:
    plan = routine.begin()
    while True:
        detail = execute_detail(session, plan, send)
        moving = bool(plan.calls) and plan.calls[-1].command.startswith("G1")
        sample = None
        if moving and not detail.halted:
            sample = _while_moving(session, routine, send, write)
        for line in detail.replies:
            write(line)
        if detail.halted:
            return False
        if routine.phase in {"fail", "done"}:
            return routine.phase == "done"
        if sample is None:
            sample = Sample(True, axis_stalled(detail.last_body, routine.axis))
        plan = routine.advance(sample)


def _while_moving(session, routine: Calibrator, send, write) -> Sample:
    """Lee la carga mientras el paso sigue en marcha. En reposo sg_result es 0."""
    travel = routine.step_mm / routine.feed * 60.0
    deadline = time.monotonic() + travel + 0.25
    time.sleep(travel * 0.25)
    while time.monotonic() < deadline:
        body = send("M122", session.bench.consulta_s)
        text = body if isinstance(body, str) else str(body)
        sg, _moving = load_sample(text, routine.axis)
        if sg is not None:
            write(f"{routine.axis} sg {sg}")
        if stalled_load(sg, routine.umbral_stall):
            send("M410", session.bench.consulta_s)
            send("M17", session.bench.consulta_s)
            write(
                f"StallGuard {routine.axis} {sg} bajo {routine.umbral_stall}. "
                "Se frena y se sostiene la corriente."
            )
            return Sample(True, True)
        time.sleep(0.02)
    body = send("M119", session.bench.consulta_s)
    text = body if isinstance(body, str) else str(body)
    stalled = axis_stalled(text, routine.axis)
    if stalled:
        send("M410", session.bench.consulta_s)
        send("M17", session.bench.consulta_s)
        write(f"M119 {routine.axis} TRIGGERED. Se frena y se sostiene la corriente.")
        return Sample(True, True)
    send("M400", session.bench.consulta_s)
    return Sample(True, stalled)
