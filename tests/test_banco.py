"""La suite lee config/banco.toml y no abre el puerto en estas pruebas."""

from dataclasses import replace

import pytest

from tonf.banco import ConfigError, Step, build, describe, execute, load_path, load_text, replace_channel
from tonf.__main__ import main

ROOT_CONFIG = load_path()


def _commands(program, group: str | None = None) -> list[str]:
    return [step.command for step in program.steps if group is None or step.group == group]


def test_la_calibracion_sale_del_archivo():
    assert ROOT_CONFIG.paso_mm == 30
    assert ROOT_CONFIG.avance_busqueda_mm_min == 1800
    assert ROOT_CONFIG.avance_mm_min == 300
    assert ROOT_CONFIG.margen_mm == 2
    assert ROOT_CONFIG.sonda_mm == 1
    assert ROOT_CONFIG.sin_topes_mm == 10
    text = describe(ROOT_CONFIG, "X")
    assert "Calibración: paso 30 mm" in text


def test_un_paso_de_calibracion_en_cero_no_carga():
    source = ROOT_CONFIG.path.read_text(encoding="utf-8").replace("paso_mm = 30", "paso_mm = 0", 1)
    with pytest.raises(ConfigError, match="paso_mm"):
        load_text(source)


def test_un_avance_de_calibracion_sobre_m203_avisa():
    text = describe(replace(ROOT_CONFIG, avance_mm_min=10_000), "X")
    assert "La calibración pide 10000 mm/min" in text


def test_el_archivo_real_tiene_los_cinco_canales_en_orden():
    assert [channel.id for channel in ROOT_CONFIG.ordered()] == ["X", "Y", "Z", "E0", "E1"]
    currents = {channel.id: channel.corriente_ma for channel in ROOT_CONFIG.channels}
    assert currents == {"X": 800, "Y": 800, "Z": 800, "E0": 800, "E1": 800}


def test_el_protocolo_de_x_sale_igual_que_la_prueba_en_vacio():
    program = build(ROOT_CONFIG)
    assert _commands(program, "X") == [
        "G90",
        "G92 X150",
        "G91",
        "G1 X-10 F300",
        "M400",
        "G1 X10 F300",
        "M400",
        "G1 X-40 F600",
        "M400",
        "G1 X40 F600",
        "M400",
        "G1 X-40 F1800",
        "M400",
        "G1 X40 F1800",
        "M400",
        "M114",
        "M122",
        "M914",
        "M119",
    ]


def test_e0_y_e1_se_mueven_con_su_nombre():
    commands = _commands(build(ROOT_CONFIG))
    assert "M906 T0 E1268" in commands
    assert "M906 T1 E800" in commands
    assert "M906 E800" not in commands
    assert _commands(build(ROOT_CONFIG), "E0")[:3] == ["T0", "M83", "G92 E150"]
    assert _commands(build(ROOT_CONFIG), "E1")[:3] == ["T1", "M83", "G92 E150"]
    assert "G1 E10 F300" in _commands(build(ROOT_CONFIG), "E0")
    assert "G1 E10 F300" in _commands(build(ROOT_CONFIG), "E1")
    assert commands[-3:] == ["G90", "T0", "M18"]


def test_la_suite_no_homea_ni_calienta():
    commands = _commands(build(ROOT_CONFIG))
    assert not any(command.split()[0] in {"G28", "M104", "M109", "M140", "M190"} for command in commands)
    assert "M203 X100 Y100 Z20 E25" in commands
    assert "M92 X80 Y80 Z400 E95" in commands
    assert "M914 X100" in commands
    assert "M914 Y100" in commands
    assert "M914 Z100" in commands
    assert "M914 T0 E100" in commands
    assert "M914 T1 E100" in commands
    assert "M302 S0" in commands
    assert "M412 S0" in commands


def test_sentido_menos_uno_invierte_el_primer_tramo():
    bench = replace_channel(ROOT_CONFIG, "X", sentido=-1)
    motion = [command for command in _commands(build(bench, "X"), "X") if command.startswith("G1")]
    assert motion[0] == "G1 X-10 F300"
    assert motion[1] == "G1 X10 F300"


def test_una_corriente_sobre_el_techo_no_arma_la_suite():
    bench = replace_channel(ROOT_CONFIG, "Y", corriente_ma=801)
    with pytest.raises(ConfigError, match="techo"):
        build(bench)


def test_un_tramo_que_sale_de_la_caja_no_se_envia():
    bench = replace_channel(ROOT_CONFIG, "X", origen_mm=4, sentido=-1)
    with pytest.raises(ConfigError, match="fuera"):
        build(bench, "X")


def test_pasos_distintos_en_e0_y_e1_se_rechazan():
    bench = replace_channel(ROOT_CONFIG, "E1", pasos_por_mm=80)
    with pytest.raises(ConfigError, match="DISTINCT_E_FACTORS"):
        build(bench)


def test_home_en_el_archivo_se_rechaza():
    with pytest.raises(ConfigError, match="no homea"):
        build(replace(ROOT_CONFIG, home=True))


def test_un_canal_inactivo_no_se_mueve_y_su_corriente_si_se_escribe():
    bench = replace_channel(ROOT_CONFIG, "Y", activo=False)
    program = build(bench)
    assert "Y" not in {step.group for step in program.steps}
    assert "M906 Y1268" in _commands(program)


def test_un_error_de_la_placa_suelta_los_motores():
    class Port:
        def __init__(self):
            self.written = []
            self.pending = b""

        def write(self, data: bytes) -> int:
            self.written.append(data.decode())
            reply = "echo: cold extrusion prevented\nok\n" if len(self.written) == 2 else "ok\n"
            self.pending = reply.encode()
            return len(data)

        def flush(self) -> None:
            return None

        def read(self, _size: int) -> bytes:
            data, self.pending = self.pending, b""
            return data

    port = Port()
    program = build(ROOT_CONFIG, "X")
    assert execute(port, program.steps[:3], settle_s=0) == 1
    assert port.written[-1] == "M18\n"


def test_cada_comando_se_anuncia_y_su_respuesta_sale_en_la_terminal(capsys):
    class Port:
        def __init__(self):
            self.pending = b""

        def write(self, data: bytes) -> int:
            self.pending = b"echo:busy: processing\nok\n"
            return len(data)

        def flush(self) -> None:
            return None

        def read(self, _size: int) -> bytes:
            data, self.pending = self.pending, b""
            return data

    assert execute(Port(), [Step("M400", 1, "X")], settle_s=0) == 0
    output = capsys.readouterr().out
    assert output.index("----- X -----") < output.index("===== M400 =====")
    assert output.index("===== M400 =====") < output.index("echo:busy: processing")
    assert "ok" in output


def test_listar_no_necesita_la_placa(capsys):
    assert main(["suite", "--listar"]) == 0
    output = capsys.readouterr().out
    assert "Canal E1" in output
    assert "CF3925-100-SL" in output
    assert "BJ42D29-16W01" in output
    assert "800 mA" in output
