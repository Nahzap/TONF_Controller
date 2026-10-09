"""Pregunta el eje al abrir el monitor y carga o corre la calibración."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime

from tonf.banco import corriente_m906
from tonf.manual.calibrate import Calibrator, Sample
from tonf.manual.drivers import parse_m114
from tonf.manual.frame import to_logical, to_marlin
from tonf.manual.model import Call, Plan, num
from tonf.manual.pace import move_timeout, sequence_wait, tramos_mm
from tonf.manual.runner import execute_detail, execute_plan
from tonf.manual.stall import (
    Caida,
    axis_stalled,
    espera_entre_muestras,
    frena_si_sigue_en_marcha,
    load_sample,
    stalled_load,
)
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
    write("Un canal en el mínimo usa ese punto como inicio. Uno libre puede partir en cualquier lugar.")
    write("El libre busca primero el máximo y después el mínimo. El punto medio queda entre esos dos topes.")
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
            held = _finish_saved(session, existing, send, write)
            if held is not None:
                return held
            write(f"Sigue {choice.axis}. Indique el siguiente eje, o CERRAR.")
            continue
        if choice.force and path.is_file():
            write(f"AVISO se repite la calibración de {choice.axis}.")
        record = _place_declared(session, choice, send, write)
        if record is None:
            return 1
        save_record(path, record)
        write(f"OK calibración guardada en {path}.")
        held = _finish_saved(session, record, send, write)
        if held is not None:
            return held
        write(f"Sigue {choice.axis}. Indique el siguiente eje, o CERRAR.")


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
    _armar_freno(send, state, channel)
    state.current_set = False
    pause = session.bench.consulta_s
    preparar = []
    if channel.arranque_mm_s2 is not None:
        preparar.append(Call(f"M201 {state.letra}{num(channel.arranque_mm_s2)}", pause))
    inicio = choice.inicio_mm
    fin = choice.fin_mm
    medio = (inicio + fin) / 2.0
    margen = session.bench.margen_mm
    techo_avance = session.bench.avances_mm_s[state.letra] * 60.0
    feed = min(session.bench.avance_busqueda_mm_min, techo_avance)
    if channel.avance_mm_min is not None:
        feed = min(feed, channel.avance_mm_min)
    elif state.pasos_por_mm >= 400:
        feed = min(feed, session.bench.avance_mm_min)
    write(
        f"{choice.axis}: corriente {choice.corriente_ma} mA, "
        f"tramo declarado {num(inicio)}…{num(fin)} mm."
    )
    if channel.partida == "libre":
        return _place_libre(session, choice, state, fin - inicio, feed, pause, margen, preparar, send, write)
    write(f"Punto medio declarado {num(medio)} mm.")
    if not _travel_to(
        session,
        state,
        fin,
        fin - inicio,
        feed,
        [
            *preparar,
            *current_calls(session, state),
            Call("G90", pause),
            Call(f"G92 {state.letra}{num(to_marlin(inicio, state.signo))}", pause),
        ],
        f"Se recorre hasta el fin {num(fin)} mm. Después se vuelve al punto medio {num(medio)} mm.",
        "no llegó al fin declarado",
        send,
        write,
    ):
        return None
    if not _travel_to(
        session,
        state,
        medio,
        fin - medio,
        feed,
        [Call("G90", pause)],
        f"Fin en {num(fin)} mm. Se va al punto medio {num(medio)} mm.",
        "el regreso al punto medio se frenó",
        send,
        write,
    ):
        write(f"AVISO {choice.axis} ya recorrió hasta el fin. Se sigue con el siguiente eje.")
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


def _place_libre(session, choice: Choice, state, alcance: float, feed: float, pause: float, margen: float, preparar: list, send, write) -> Record | None:
    write(
        f"{choice.axis} puede partir en cualquier punto. "
        f"Primero el máximo, en el sentido {state.signo:+d}. Después el mínimo."
    )
    if not _buscar_tope(
        session,
        state,
        alcance,
        alcance,
        feed,
        [
            *preparar,
            *current_calls(session, state),
            Call("G90", pause),
            Call(f"G92 {state.letra}0", pause),
        ],
        f"Busca el máximo, hasta {num(alcance)} mm desde donde está.",
        send,
        write,
    ):
        write("RECHAZADO no apareció el máximo. La corriente sigue aplicada.")
        return None
    maximo = _leer_logico(session, state, send, write)
    if maximo is None:
        return None
    write(f"Máximo a {num(maximo)} mm de la partida.")
    if not _buscar_tope(
        session,
        state,
        maximo - alcance,
        alcance,
        feed,
        [Call("G90", pause)],
        f"Busca el mínimo, hasta {num(alcance)} mm en el sentido contrario.",
        send,
        write,
    ):
        write("RECHAZADO no apareció el mínimo. La corriente sigue aplicada.")
        return None
    minimo = _leer_logico(session, state, send, write)
    if minimo is None:
        return None
    largo = maximo - minimo
    if largo <= margen * 2:
        write("RECHAZADO los dos topes quedaron demasiado juntos. La corriente sigue aplicada.")
        return None
    medio = (maximo + minimo) / 2.0
    write(f"Mínimo a {num(minimo)} mm de la partida. Longitud medida {num(largo)} mm.")
    paso = next((item.paso_sondeo_mm for item in session.bench.channels if item.id == choice.axis), None)
    if paso is not None:
        if not _volver_sin_lectura(session, state, medio - minimo, feed, paso, send, write):
            return None
    elif not _travel_to(
        session,
        state,
        medio,
        abs(medio - minimo),
        feed,
        [Call("G90", pause)],
        f"Se va al punto medio {num(medio - minimo)} mm desde el mínimo.",
        "no llegó al punto medio",
        send,
        write,
    ):
        return None
    desde_el_minimo = medio - minimo
    detail = execute_detail(
        session,
        Plan(
            [],
            [Call(f"G92 {state.letra}{num(to_marlin(desde_el_minimo, state.signo))}", pause)],
        ),
        send,
    )
    for line in detail.replies:
        write(line)
    if detail.halted:
        return None
    return Record(
        eje=choice.axis,
        fecha=datetime.now().astimezone().isoformat(timespec="seconds"),
        pasos_por_mm=state.pasos_por_mm,
        sentido=state.signo,
        corriente_ma=choice.corriente_ma,
        margen_mm=margen,
        minimo_mecanico_mm=0.0,
        maximo_mecanico_mm=largo,
        minimo_trabajo_mm=margen,
        maximo_trabajo_mm=largo - margen,
        longitud_mm=largo,
        punto_medio_mm=largo / 2.0,
        pasos_entre_topes=legal_steps(largo, state.pasos_por_mm),
        umbral_stall=state.sensibilidad_stall,
        bloqueado=True,
    )


def _paso_sondeo(session, state) -> float | None:
    for channel in session.bench.channels:
        if channel.id == state.axis_id:
            return channel.paso_sondeo_mm
    return None


def _buscar_tope(session, state, mm: float, distance: float, feed: float, prefix: list, message: str, send, write) -> bool:
    paso = _paso_sondeo(session, state)
    if paso is not None:
        return _buscar_por_pasos(session, state, mm, distance, feed, prefix, message, paso, send, write)
    pause = session.bench.consulta_s
    timeout = move_timeout(distance, feed, pause, sequence_wait(session.bench, state.axis_id))
    plan = Plan(
        [message],
        [*prefix, Call(f"G1 {state.letra}{num(to_marlin(mm, state.signo))} F{num(feed)}", timeout)],
    )
    detail = execute_detail(session, plan, send)
    stalled = False
    if not detail.halted:
        stalled = _watch_travel(session, state, distance, feed, send, write, buscar=True)
    for line in detail.replies:
        write(line)
    return (not detail.halted) and stalled


def _caida_de(session, state) -> Caida:
    fraccion = session.bench.fraccion_caida
    piso = state.sensibilidad_stall
    for channel in session.bench.channels:
        if channel.id != state.axis_id:
            continue
        if channel.fraccion_caida is not None:
            fraccion = channel.fraccion_caida
        if channel.piso_marcha is not None:
            piso = channel.piso_marcha
    return Caida(state.sensibilidad_stall, fraccion, session.bench.muestras_caida, piso)


def _buscar_por_pasos(session, state, mm: float, distance: float, feed: float, prefix: list, message: str, paso: float, send, write) -> bool:
    """Busca el metal de a un tramo. El reposo al acabar la orden no cuenta como tope."""
    pause = session.bench.consulta_s
    detail = execute_detail(session, Plan([message], list(prefix)), send)
    for line in detail.replies:
        write(line)
    if detail.halted:
        return False
    origen = _leer_logico(session, state, send, write)
    if origen is None:
        return False
    sentido = 1 if mm >= origen else -1
    caida = _caida_de(session, state)
    recorrido = 0.0
    while recorrido + 1e-6 < distance:
        tramo = min(paso, distance - recorrido)
        destino = origen + sentido * (recorrido + tramo)
        timeout = move_timeout(tramo, feed, pause, sequence_wait(session.bench, state.axis_id))
        detail = execute_detail(
            session,
            Plan(
                [],
                [
                    Call("G90", pause),
                    Call(f"M906 {state.letra}{state.m906_ma}", pause),
                    Call(f"G1 {state.letra}{num(to_marlin(destino, state.signo))} F{num(feed)}", timeout),
                ],
            ),
            send,
        )
        for line in detail.replies:
            write(line)
        if detail.halted:
            return False
        if feed > 0:
            time.sleep(min(tramo / feed * 60.0 * 0.2, 0.4))

        def decidir(sg: int | None, moving: bool | None = None) -> bool:
            return frena_si_sigue_en_marcha(caida, sg, moving)

        try:
            body = _leer_carga(send, state.axis_id, pause, decidir, write)
        except Exception:
            if getattr(send, "frenado", False):
                write(f"{state.axis_id} se frenó al ver el tope. Después se cortó el puerto.")
                return True
            return _frenar(session, send, write, f"{state.axis_id} perdió el puerto contra el recorrido.")
        if getattr(send, "frenado", False):
            write(f"Tope de {state.axis_id}. El freno salió al leer la caída.")
            return True
        if getattr(send, "vigilar", None) is None:
            text = body if isinstance(body, str) else str(body)
            sg, moving = load_sample(text, state.axis_id)
            if sg is not None:
                write(f"{state.axis_id} sg {sg}")
            if decidir(sg, moving):
                return _frenar(session, send, write, f"StallGuard {state.axis_id} {sg}, pico {caida.pico}.")
        try:
            send("M400", timeout)
            _corriente_de_reposo(session, send)
        except Exception:
            return _frenar(session, send, write, f"{state.axis_id} perdió el puerto al cerrar el tramo.")
        recorrido += tramo
    _corriente_de_reposo(session, send)
    return False


def _leer_logico(session, state, send, write) -> float | None:
    try:
        body = send("M114", session.bench.consulta_s)
    except Exception:
        write("RECHAZADO no se pudo leer la posición del tope.")
        return None
    marlin = parse_m114(str(body)).get(state.letra)
    if marlin is None:
        write(f"RECHAZADO M114 no trajo {state.letra}.")
        return None
    return to_logical(marlin, state.signo)


def _volver_sin_lectura(session, state, distancia_mm: float, feed: float, paso: float, send, write) -> bool:
    """Regreso al medio sin M122. Leer el driver en ese tramo deja el husillo en el extremo."""
    pause = session.bench.consulta_s
    marlin = to_marlin(distancia_mm, state.signo)
    write(
        f"Vuelve {num(abs(distancia_mm))} mm al punto medio, "
        f"en tramos de {num(paso)} mm, sin leer el driver."
    )
    calls = [Call(f"M906 {state.letra}{state.m906_ma}", pause), Call("G91", pause)]
    for tramo in tramos_mm(marlin, paso):
        timeout = move_timeout(abs(tramo), feed, pause, sequence_wait(session.bench, state.axis_id))
        calls.append(Call(f"G1 {state.letra}{num(tramo)} F{num(feed)}", timeout))
        calls.append(Call("M400", timeout))
    calls.append(Call("G90", pause))
    detail = execute_detail(session, Plan([], calls), send)
    for line in detail.replies:
        write(line)
    if detail.halted:
        write("RECHAZADO no llegó al punto medio. La corriente sigue aplicada.")
        return False
    _corriente_de_reposo(session, send)
    return True


def _travel_to(session, state, mm: float, distance: float, feed: float, prefix: list, message: str, failure: str, send, write) -> bool:
    pause = session.bench.consulta_s
    timeout = move_timeout(distance, feed, pause, sequence_wait(session.bench, state.axis_id))
    plan = Plan(
        [message],
        [
            *prefix,
            Call(f"G1 {state.letra}{num(to_marlin(mm, state.signo))} F{num(feed)}", timeout),
        ],
    )
    detail = execute_detail(session, plan, send)
    stalled = False
    if not detail.halted:
        stalled = _watch_travel(session, state, distance, feed, send, write, buscar=False)
    for line in detail.replies:
        write(line)
    if detail.halted or stalled:
        write(f"RECHAZADO {failure}. La corriente sigue aplicada.")
        return False
    return True


def _orden_tope(state, channel) -> str | None:
    if channel.corriente_tope_ma is None:
        return None
    ma = corriente_m906(replace(channel, corriente_ma=channel.corriente_tope_ma))
    return f"M906 {state.letra}{ma}\n"


def _armar_freno(send, state, channel) -> None:
    orden = _orden_tope(state, channel)
    puerto = getattr(send, "puerto", None)
    if orden is None or puerto is None:
        return
    puerto.al_frenar = orden.encode("ascii")


def _corriente_de_reposo(session, send) -> None:
    """Parado no se queda en la corriente de marcha."""
    puerto = getattr(send, "puerto", None)
    orden = getattr(puerto, "al_frenar", None) if puerto is not None else None
    if not orden:
        return
    texto = orden.decode("ascii").strip() if isinstance(orden, bytes) else str(orden).strip()
    send(texto, session.bench.consulta_s)


def _frenar(session, send, write, motivo: str) -> bool:
    try:
        puerto = getattr(send, "puerto", None)
        orden = getattr(puerto, "al_frenar", None) if puerto is not None else None
        if orden:
            send(orden.decode("ascii").strip(), session.bench.consulta_s)
        send("M410", session.bench.consulta_s)
        send("M17", session.bench.consulta_s)
        write(f"{motivo} Se frena y la corriente de tope no pasa de la consigna.")
    except Exception:
        write(f"{motivo} Se cortó el puerto antes de poder frenar.")
    return True


def _leer_carga(send, axis: str, timeout: float, decidir, write):
    """M122. Si el puerto sabe vigilar, el M410 sale al leer sg_result, sin esperar el resto.

    decidir recibe la carga y si el eje sigue en marcha. El reposo no es tope.
    """
    vigilar = getattr(send, "vigilar", None)
    if vigilar is None:
        return send("M122", timeout)
    acum: list[str] = []

    def vigia(line: str) -> bool:
        acum.append(line)
        if "sg_result" not in line.lower():
            return False
        sg, moving = load_sample("\n".join(acum), axis)
        if sg is not None:
            write(f"{axis} sg {sg}")
        return decidir(sg, moving)

    body = vigilar("M122", timeout, vigia)
    puerto = getattr(send, "puerto", None)
    send.frenado = bool(getattr(puerto, "frenado", False))
    return body


def _watch_travel(session, state, distance_mm: float, feed: float, send, write, buscar: bool) -> bool:
    """True si el eje atasca antes de terminar el tramo. La corriente sigue.

    En una búsqueda de tope, una caída frente al pico también frena.
    En un fin ya declarado, solo frena si la carga baja del umbral.
    """
    travel = 0.0 if feed <= 0 else abs(distance_mm) / feed * 60.0
    deadline = time.monotonic() + travel + 0.25
    fraccion = session.bench.fraccion_caida
    for channel in session.bench.channels:
        if channel.id == state.axis_id and channel.fraccion_caida is not None:
            fraccion = channel.fraccion_caida
    piso = state.sensibilidad_stall
    paso = None
    for channel in session.bench.channels:
        if channel.id != state.axis_id:
            continue
        if channel.piso_marcha is not None:
            piso = channel.piso_marcha
        paso = channel.paso_sondeo_mm
    caida = Caida(state.sensibilidad_stall, fraccion, session.bench.muestras_caida, piso)
    espera = espera_entre_muestras(feed, paso, travel)

    def decidir(sg: int | None, moving: bool | None = None) -> bool:
        if moving is False:
            return False
        if buscar:
            return frena_si_sigue_en_marcha(caida, sg, moving)
        return stalled_load(sg, state.sensibilidad_stall)
    time.sleep(min(espera, travel) if paso is not None else min(travel * 0.25, 0.2))
    while time.monotonic() < deadline:
        try:
            body = _leer_carga(send, state.axis_id, session.bench.consulta_s, decidir, write)
        except Exception:
            if getattr(send, "frenado", False):
                write(f"{state.axis_id} se frenó al ver el tope. Después se cortó el puerto.")
                return True
            return _frenar(session, send, write, f"{state.axis_id} perdió el puerto contra el recorrido.")
        if getattr(send, "frenado", False):
            write(f"Tope de {state.axis_id}. El freno salió al leer la caída.")
            return True
        text = body if isinstance(body, str) else str(body)
        sg, moving = load_sample(text, state.axis_id)
        if sg is not None:
            write(f"{state.axis_id} sg {sg}")
        if decidir(sg, moving):
            return _frenar(session, send, write, f"StallGuard {state.axis_id} {sg}, pico {caida.pico}.")
        time.sleep(espera)
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
    caida = Caida(routine.umbral_stall, session.bench.fraccion_caida, session.bench.muestras_caida)
    time.sleep(travel * 0.25)
    while time.monotonic() < deadline:
        body = send("M122", session.bench.consulta_s)
        text = body if isinstance(body, str) else str(body)
        sg, _moving = load_sample(text, routine.axis)
        if sg is not None:
            write(f"{routine.axis} sg {sg}")
        if caida.toma(sg):
            send("M410", session.bench.consulta_s)
            send("M17", session.bench.consulta_s)
            write(
                f"StallGuard {routine.axis} {sg}, pico {caida.pico}. "
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
