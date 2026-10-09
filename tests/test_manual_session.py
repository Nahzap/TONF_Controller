"""El protocolo rechaza un paso que saldría del riel antes de armar G-code."""

from tonf.banco import load_path
from tonf.manual.drivers import DriverReport
from tonf.manual.session import MenuSession

ROOT = load_path()


def _commands(plan) -> list[str]:
    return [call.command for call in plan.calls]


def _ready_x() -> MenuSession:
    session = MenuSession(ROOT)
    session.note_drivers({"X": DriverReport(True, "OK")})
    session.apply(session.plan("USAR X"))
    session.apply(session.plan("REF X 150"))
    return session


def test_el_arranque_no_mueve_ningun_eje():
    commands = _commands(MenuSession(ROOT).startup_plan())
    assert commands[0] == "M115"
    assert "M122" in commands
    assert "G28" not in commands
    assert not any(command.startswith("G1") or command.startswith("G0") for command in commands)


def test_y_y_e0_no_reciben_pasos():
    session = _ready_x()
    blocked = session.plan("M Y 80")
    assert blocked.calls == []
    assert "bloqueado" in blocked.replies[0]
    extruder = session.plan("PERMITIR E0")
    assert extruder.calls == []
    assert "riel" in extruder.replies[0]


def test_m_sin_limites_no_genera_g1():
    session = _ready_x()
    plan = session.plan("M X 80")
    assert plan.calls == []
    assert "mínimo y máximo" in plan.replies[0]


def test_lim_sin_confirmar_deja_m_bloqueado():
    session = _ready_x()
    proposed = session.plan("LIM X 20 280")
    assert "M sigue bloqueado" in proposed.replies[0]
    plan = session.plan("M X 80")
    assert plan.calls == []


def test_m_dentro_de_la_ventana_traduce_pasos_a_g1_absoluto():
    session = _ready_x()
    session.plan("LIM X 20 280 CONFIRMAR")
    plan = session.plan("M X 800")
    assert "G1 X-160 F300" in _commands(plan)
    assert "M400" in _commands(plan)
    assert "M18 Y Z E" in _commands(plan)
    assert not any(command.startswith("G28") for command in _commands(plan))


def test_m_que_pasa_el_maximo_no_envia_movimiento():
    session = _ready_x()
    session.plan("LIM X 20 280 CONFIRMAR")
    plan = session.plan("M X 10401")
    assert plan.calls == []
    assert "No se envió el movimiento" in plan.replies[0]


def test_sin_topes_mecanicos_un_m_largo_se_corta_a_10_mm():
    session = _ready_x()
    session.plan("LIM X 20 280 CONFIRMAR")
    plan = session.plan("M X 801")
    assert plan.calls == []
    assert "10 mm" in plan.replies[0]


def test_la_sonda_no_acepta_mas_de_1_mm():
    session = _ready_x()
    plan = session.plan("P X -81")
    assert plan.calls == []
    assert "1 mm" in plan.replies[0]
    short = session.plan("P X -80")
    assert "G1 X-149 F300" in _commands(short)


def test_el_tope_minimo_retrocede_el_margen_y_no_vuelve_a_entrar():
    session = _ready_x()
    plan = session.plan("TOPE X MIN")
    assert "G1 X-152 F300" in _commands(plan)
    session.apply(plan)
    assert session.axes["X"].mechanical_min == 150
    assert session.axes["X"].soft_min == 152
    assert session.axes["X"].position_mm == 152
    back = session.plan("P X -8")
    assert back.calls == []
    assert "No se envió el movimiento" in back.replies[0]


def test_con_los_dos_topes_m_puede_recorrer_el_interior():
    session = _ready_x()
    session.apply(session.plan("TOPE X MIN"))
    for _ in range(8):
        session.apply(session.plan("P X 80"))
    assert session.axes["X"].position_mm == 160
    session.apply(session.plan("TOPE X MAX"))
    state = session.axes["X"]
    assert state.mechanical_max == 160
    assert state.soft_max == 158
    assert state.position_mm == 158
    assert state.soft_min == 152
    inside = session.plan("M X -400")
    assert "G1 X-153 F300" in _commands(inside)
    outside = session.plan("M X 80")
    assert outside.calls == []


def test_x_con_carga_abierta_no_se_mueve_hasta_forzar():
    session = MenuSession(ROOT)
    session.note_drivers({"X": DriverReport(True, "OK", ola=True)})
    refused = session.plan("REF X 150")
    assert refused.calls == []
    assert "carga abierta" in refused.replies[0]
    session.plan("FORZAR X")
    allowed = session.plan("REF X 150")
    assert any(command.startswith("G92 X-150") for command in _commands(allowed))
