"""Pasos y ventana de recorrido, sin la sesión ni el puerto."""

from tonf.manual.steps import legal_steps, steps_to_mm
from tonf.manual.window import rejection_if_outside, rejection_if_probe_too_long


def test_800_pasos_de_x_son_10_mm():
    assert steps_to_mm(800, 80) == 10
    assert steps_to_mm(-80, 80) == -1
    assert legal_steps(10, 80) == 800
    assert legal_steps(-0.0125, 80) == -1


def test_un_destino_fuera_de_ventana_no_tiene_pasos_de_sobra():
    text = rejection_if_outside(150, 281, 20, 280, 80)
    assert text is not None
    assert "280" in text
    assert "caben 10400 pasos" in text
    assert rejection_if_outside(150, 160, 20, 280, 80) is None


def test_la_sonda_no_pasa_de_un_milimetro():
    assert rejection_if_probe_too_long(80, 80, 1) is None
    text = rejection_if_probe_too_long(81, 80, 1)
    assert text is not None
    assert "80 pasos" in text
