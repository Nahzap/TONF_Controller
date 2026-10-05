from datetime import datetime

import pytest

from tonf.gcode import lines_from_text, stream_lines, stream_program
from tonf.guard import UnsafeCommand, guard
from tonf.link import Link, ScriptedPort
from tonf.measure import live_indicators
from tonf.model import Suite
from tonf.parse import parse_m115, parse_m119, percentile
from tonf.ports import PortInfo, selectable
from tonf.report import render


def _port(device: str, description: str = "USB Serial Device", vid: int | None = 0x1D50, product: str = "") -> PortInfo:
    return PortInfo(device, description, "USB VID:PID", vid, 0x6015, "", product)


def test_un_solo_usb_se_elige():
    chosen, reason = selectable([_port("COM4", vid=0x2341, product="")], None)
    assert [port.device for port in chosen] == ["COM4"]
    assert "Un solo USB" in reason


def test_varios_usb_genericos_no_se_abren():
    ports = [_port("COM4", vid=0x2341), _port("COM5", vid=0x2341)]
    chosen, reason = selectable(ports, None)
    assert chosen == []
    assert "COM4" in reason and "COM5" in reason


def test_pista_klipper_desambigua():
    ports = [
        _port("COM4", vid=0x2341, product="otro"),
        _port("COM7", vid=0x1D50, product="Klipper"),
    ]
    chosen, _reason = selectable(ports, None)
    assert [port.device for port in chosen] == ["COM7"]


def test_comando_de_movimiento_no_sale():
    port = ScriptedPort(replies={})
    link = Link(port, 115200, "COM4")
    with pytest.raises(UnsafeCommand):
        link.transact("G0 X10")
    assert port.written == []
    guard("M115")


def test_m115_y_m119():
    fields = parse_m115(
        [
            "FIRMWARE_NAME:Marlin 2.1.2 (05-10-2026) SOURCE_CODE_URL:github.com/MarlinFirmware/Marlin PROTOCOL_VERSION:1.0 MACHINE_TYPE:3D Printer EXTRUDER_COUNT:0 UUID:abc",
            "Cap:EEPROM:1",
            "ok",
        ]
    )
    assert fields["FIRMWARE_NAME"].startswith("Marlin 2.1.2")
    assert fields["MACHINE_TYPE"] == "3D Printer"
    assert fields["EXTRUDER_COUNT"] == "0"
    assert "EEPROM:1" in fields["CAPACIDADES"]
    assert parse_m119(["Reporting endstop status", "x_min: open", "y_min: TRIGGERED", "ok"]) == {
        "x_min": "open",
        "y_min": "TRIGGERED",
    }


def test_suite_marlin_en_puerto_falso():
    replies = {
        "M115": [
            "FIRMWARE_NAME:Marlin 2.1.2 SOURCE_CODE_URL:https://example PROTOCOL_VERSION:1.0 MACHINE_TYPE:TONF EXTRUDER_COUNT:0 UUID:abc",
            "Cap:EEPROM:0",
            "ok",
        ],
        "M114": ["X:0.00 Y:0.00 Z:0.00 E:0.00 Count X:0 Y:0 Z:0", "ok"],
        "M119": ["x_min: open", "y_min: open", "z_min: open", "ok"],
    }
    link = Link(ScriptedPort(replies=replies), 115200, "COM4")
    indicators = live_indicators(link, ["start"], samples=4)
    by_id = {item.id: item for item in indicators}
    assert by_id["protocolo"].valor == "marlin"
    assert by_id["identidad"].estado == "medido"
    assert by_id["latencia"].estado == "medido"
    assert by_id["finales"].valor.startswith("x_min=open")
    assert "G0" not in port_commands(link)
    assert set(port_commands(link)) <= {"M115", "M114", "M119"}


def test_informe_marca_bloqueado():
    suite = Suite()
    text = render(suite, datetime(2026, 10, 5, 12, 20, 0))
    assert "2026-10-05 12:20:00" in text
    assert "solo lectura" in text


def port_commands(link: Link) -> list[str]:
    return link.port.written  # type: ignore[attr-defined]


def test_gcode_existente_se_limpia_como_grbl():
    lines = lines_from_text("g0 x0 y0\nG1 X10 (avance) Y2 F300 ; cola\n%\n\n(solo nota)\n")
    assert lines == ["G0 X0 Y0", "G1 X10 Y2 F300"]


def test_envio_grbl_linea_y_ok():
    port = ScriptedPort(replies={"G1 X1": ["error:33"]})
    link = Link(port, 115200, "COM4")
    result = stream_lines(link, ["G0 X0", "G1 X1", "G1 X2"])
    assert port.written == ["G0 X0", "G1 X1"]
    assert result.ok == 1
    assert "error:33" in result.stopped


def test_comprobar_usa_el_modo_c_de_grbl():
    port = ScriptedPort(replies={})
    link = Link(port, 115200, "COM4")
    result = stream_program(link, ["G1 X1 F100"], comprobar=True)
    assert port.written == ["$C", "G1 X1 F100", "$C"]
    assert result.ok == 1


def test_percentil():
    assert percentile([0.1], 0.95) == 0.1
    assert percentile([0.01, 0.02, 0.03, 0.04], 0.5) == 0.02
