"""La autocalibración usa el archivo y no abre el puerto."""

from dataclasses import replace

from tonf.banco import load_path, replace_channel
from tonf.manual.boot import Choice, ask_axis, install
from tonf.manual.calibrate import Calibrator, Sample
from tonf.manual.drivers import DriverReport
from tonf.manual.model import num
from tonf.manual.runner import serve
from tonf.manual.session import MenuSession
from tonf.manual.store import Record, load_record, record_path, save_record

ROOT = load_path()


def _commands(cal: Calibrator, flags: list[bool]) -> list[str]:
    plan = cal.begin()
    commands = [call.command for call in plan.calls]
    for stalled in flags:
        if cal.phase in {"fail", "done"}:
            break
        plan = cal.advance(Sample(True, stalled))
        commands.extend(call.command for call in plan.calls)
    return commands


def _routine(session: MenuSession, step: float, margin: float, span: float) -> Calibrator:
    state = session.axes["X"]
    return Calibrator.create(
        state,
        session.bench.consulta_s,
        span,
        margin,
        step,
        session.bench.avance_mm_min,
        20,
    )


def _g1(target: float, feed: float) -> str:
    return f"G1 X{num(target)} F{num(feed)}"


def test_el_primer_paso_y_el_sentido_salen_del_archivo():
    session = MenuSession(ROOT)
    state = session.axes["X"]
    assert state.signo == -1
    routine = Calibrator.create(
        state,
        session.bench.consulta_s,
        state.compiled_max - state.compiled_min,
        session.bench.margen_mm,
        session.bench.paso_mm,
        session.bench.avance_mm_min,
        20,
    )
    plan = routine.advance(Sample(True, False))
    assert _g1(-session.bench.paso_mm, session.bench.avance_mm_min) in [call.command for call in plan.calls]


def test_si_el_primer_paso_atasca_el_sentido_se_invierte():
    session = MenuSession(replace_channel(ROOT, "X", sentido=-1))
    feed = session.bench.avance_mm_min
    routine = _routine(session, 1, 1, 20)
    commands = _commands(routine, [False, True, False])
    assert _g1(-1, feed) in commands
    assert _g1(1, feed) in commands
    assert routine.signo == 1
    assert routine.phase == "step"


def test_el_atasco_despues_de_subir_es_el_maximo_y_queda_en_el_medio():
    session = MenuSession(ROOT)
    feed = session.bench.avance_mm_min
    routine = _routine(session, 1, 1, 20)
    commands = _commands(routine, [False, False, False, False, True, False, False])
    assert [_g1(target, feed) for target in (-1, -2, -3, -4, 2, -1.5)] == [
        command for command in commands if command.startswith("G1")
    ]
    assert routine.phase == "done"
    assert routine.signo == -1
    record = routine.to_record(fecha="2026-10-09T14:00:00-03:00")
    assert record.longitud_mm == 3
    assert record.punto_medio_mm == 1.5
    assert record.minimo_trabajo_mm == 1
    assert record.maximo_trabajo_mm == 2
    assert record.bloqueado is True
    assert "M17" in commands
    assert "M18" not in commands


def test_si_tampoco_sube_al_reves_se_sostiene():
    session = MenuSession(ROOT)
    routine = _routine(session, 1, 1, 20)
    commands = _commands(routine, [False, True, True])
    assert routine.phase == "fail"
    assert "contrario" in routine.error
    assert commands[-2:] == ["M410", "M17"]
    assert "M18" not in commands


def test_sin_maximo_dentro_del_recorrido_no_sigue():
    session = MenuSession(ROOT)
    routine = _routine(session, 1, 1, 2)
    commands = _commands(routine, [False, False, False])
    assert routine.phase == "fail"
    assert "recorrido" in routine.error
    assert _g1(3, session.bench.avance_mm_min) not in commands


def test_un_riel_mas_corto_que_el_margen_no_se_guarda():
    session = MenuSession(ROOT)
    routine = _routine(session, 1, 1, 20)
    _commands(routine, [False, False, True])
    assert routine.phase == "fail"
    assert "margen" in routine.error


def test_el_json_vuelve_a_leerse_y_uno_roto_no(tmp_path):
    path = tmp_path / "X.json"
    record = _record()
    save_record(path, record)
    loaded = load_record(path)
    assert loaded is not None
    assert loaded.sentido == -1
    assert loaded.punto_medio_mm == 10
    path.write_text("{", encoding="utf-8")
    assert load_record(path) is None
    path.write_text('{"eje": "E0"}\n', encoding="utf-8")
    assert load_record(path) is None


def test_con_sentido_medido_menos_uno_m_va_hacia_el_maximo_en_negativo():
    session = MenuSession(ROOT)
    session.note_drivers({"X": DriverReport(True, "OK")})
    install(session, _record())
    plan = session.plan("M X 80")
    assert _g1(-11, session.bench.avance_mm_min) in [call.command for call in plan.calls]


def test_anular_borra_el_json_y_devuelve_el_sentido_del_archivo(tmp_path):
    session = MenuSession(ROOT)
    session.bench = replace(session.bench, path=tmp_path / "banco.toml")
    session.note_drivers({"X": DriverReport(True, "OK")})
    save_record(record_path(session.bench.path, "X"), _record())
    install(session, _record())
    plan = session.plan("ANULAR X")
    assert not record_path(session.bench.path, "X").is_file()
    assert "json" in plan.replies[0]
    assert session.axes["X"].signo == session.axes["X"].sentido_config


def test_apagar_vuelve_al_minimo_y_despues_suelta():
    session = MenuSession(ROOT)
    install(session, _record())
    plan = session.plan("APAGAR")
    commands = [call.command for call in plan.calls]
    assert commands[0] == "G90"
    assert commands[1] == "G1 X0 F300"
    assert commands[-2] == "M400"
    assert commands[-1] == "M18"
    assert plan.quit is True


def test_la_pregunta_acepta_x_con_exclamacion():
    lines = iter(["", "e0", "x! 800 0 300"])
    out = []
    choice = ask_axis(lambda _prompt: next(lines), out.append)
    assert choice == Choice("X", True, 800, 0.0, 300.0)
    assert any("RECHAZADO" in line for line in out)


def test_si_hay_json_no_repite_la_rutina(tmp_path):
    session = _session(tmp_path)
    save_record(record_path(session.bench.path, "X"), _record())
    sent = []
    out = []
    answers = iter(["X", "CERRAR"])
    code = serve(session, _send(sent, []), lambda _prompt: next(answers), out.append)
    assert code == 0
    assert "G92 X-10" in sent
    assert "G1 X0 F300" in sent
    assert "M914 X0" in sent
    assert "M84 S0" in sent
    assert "M17" in sent
    assert any("No se repite" in line for line in out)
    assert session.axes["X"].signo == -1
    assert session.axes["X"].position_mm == 10


def test_x_admiracion_que_no_sube_en_ningun_sentido_no_pisa_el_json(tmp_path):
    session = _session(tmp_path)
    path = record_path(session.bench.path, "X")
    save_record(path, _record(fecha="guardado"))
    sent = []
    out = []
    answers = iter(["X! 800 0 20"])
    code = serve(
        session,
        _send_atasco(sent),
        lambda _prompt: next(answers),
        out.append,
    )
    assert code == 1
    assert any("punto medio" in line for line in out)
    assert load_record(path) is not None
    assert load_record(path).fecha == "guardado"


def test_calibrar_guarda_el_json_y_bloquea_en_el_medio(tmp_path):
    session = _session(tmp_path)
    sent = []
    out = []
    answers = iter(["X 700 0 20", "CERRAR"])
    code = serve(
        session,
        _placa(sent, lambda _g1: False),
        lambda _prompt: next(answers),
        out.append,
    )
    assert code == 0
    path = record_path(session.bench.path, "X")
    record = load_record(path)
    assert record is not None
    assert record.longitud_mm == 20
    assert record.punto_medio_mm == 10
    assert record.corriente_ma == 700
    assert record.minimo_mecanico_mm == 0
    assert record.maximo_mecanico_mm == 20
    assert record.margen_mm == session.bench.margen_mm
    assert record.bloqueado is True
    feed = session.bench.avance_busqueda_mm_min
    assert _g1(-20, feed) in sent
    assert _g1(-10, feed) in sent
    assert "G1 X0 F300" in sent
    assert "M906 X4550" in sent
    assert "M17" in sent
    assert not any(command.split()[0] == "G28" for command in sent)
    assert session.axes["X"].position_mm == 10
    assert any("calibración guardada" in line for line in out)


def _session(tmp_path) -> MenuSession:
    session = MenuSession(ROOT)
    session.bench = replace(session.bench, path=tmp_path / "banco.toml", paso_mm=1, margen_mm=1)
    return session


def _send(sent: list[str], m119: list[str]):
    answers = iter(m119)

    def send(command, _timeout):
        sent.append(command)
        if command == "M115":
            return "FIRMWARE_NAME:Marlin 2.1.2\nok\n"
        if command == "M122":
            return "Testing X connection... OK\nok\n"
        if command == "M119":
            return f"x_min: {next(answers)}\nok\n"
        return "ok\n"

    return send


def _placa(sent: list[str], stalled):
    last = {"g1": ""}

    def send(command, _timeout):
        sent.append(command)
        if command.startswith("G1 "):
            last["g1"] = command
        if command == "M115":
            return "FIRMWARE_NAME:Marlin 2.1.2\nok\n"
        if command == "M122":
            return "Testing X connection... OK\nok\n"
        if command == "M119":
            state = "TRIGGERED" if stalled(last["g1"]) else "open"
            return f"x_min: {state}\nok\n"
        return "ok\n"

    return send


def _send_atasco(sent: list[str]):
    return _placa(sent, lambda g1: g1.startswith("G1 "))


def _send_hasta(sent: list[str], mark: str):
    return _placa(sent, lambda g1: mark in g1)


def _record(**changes) -> Record:
    data = dict(
        eje="X",
        fecha="2026-10-09T14:00:00-03:00",
        pasos_por_mm=80,
        sentido=-1,
        corriente_ma=450,
        margen_mm=2,
        minimo_mecanico_mm=0,
        maximo_mecanico_mm=20,
        minimo_trabajo_mm=2,
        maximo_trabajo_mm=18,
        longitud_mm=20,
        punto_medio_mm=10,
        pasos_entre_topes=1600,
        umbral_stall=100,
        bloqueado=True,
    )
    data.update(changes)
    return Record(**data)
