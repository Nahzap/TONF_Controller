"""Reconocimiento de drivers, sin abrir el puerto."""

from tonf.manual.drivers import parse_m114, parse_m122
from tonf.manual.stall import load_sample, stalled_load


def test_m122_reconoce_x_y_marca_ola_solo_en_su_columna():
    body = "\n".join(
        [
            "Testing X connection... OK",
            "Testing Y connection... Error: All LOW",
            "Testing Z connection... Error: All LOW",
            "Testing E connection... Error: All LOW",
            "Testing E1 connection... Error: All LOW",
            "ola\t\t*",
            "ok",
        ]
    )
    reports, ambiguous = parse_m122(body)
    assert reports["X"].uart_ok is True
    assert reports["X"].ola is False
    assert reports["Y"].uart_ok is False
    assert reports["Y"].detail == "Error: All LOW"
    assert reports["Y"].ola is True
    assert reports["Z"].ola is False
    assert ambiguous == []


def test_una_falla_sin_columna_no_se_copia_a_x():
    reports, ambiguous = parse_m122("Testing X connection... OK\nola *\nok\n")
    assert reports["X"].uart_ok is True
    assert reports["X"].ola is False
    assert ambiguous == ["ola"]


def test_sg_result_en_marcha_es_carga_y_en_reposo_no():
    moving = "sg_result\t40\t200\t10\t0\t0\ntstep\t180\tmax\t90\tmax\tmax\nok\n"
    assert load_sample(moving, "X") == (40, True)
    assert load_sample(moving, "Y") == (200, False)
    assert load_sample("sg_result\t0\t0\ntstep\tmax\tmax\nok\n", "X") == (0, False)
    assert load_sample("ok\n", "X") == (None, None)


def test_una_carga_baja_distinta_de_cero_es_el_tope():
    assert stalled_load(36, 100) is True
    assert stalled_load(106, 100) is False
    assert stalled_load(0, 100) is False
    assert stalled_load(None, 100) is False


def test_m114_toma_la_posicion_logica_y_no_el_count():
    body = "X:150.00 Y:0.00 Z:0.00 E:0.00 Count X:12000 Y:0 Z:0\nok\n"
    assert parse_m114(body)["X"] == 150.0
