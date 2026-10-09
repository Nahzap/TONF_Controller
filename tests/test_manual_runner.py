"""El lazo serial ejecuta el plan y no inventa movimiento."""

from tonf.banco import load_path
from tonf.manual.model import Call, Plan
from tonf.manual.runner import execute_plan, serve
from tonf.manual.session import MenuSession


def test_el_runner_no_deja_salir_un_home():
    session = MenuSession(load_path())
    sent = []
    replies = execute_plan(session, Plan([], [Call("G28", 1)]), sent.append)
    assert sent == []
    assert "no envía" in replies[0]


def test_el_menu_reconoce_x_y_cierra_sin_mover():
    session = MenuSession(load_path())
    sent = []

    def send(command, _timeout):
        sent.append(command)
        if command == "M115":
            return "FIRMWARE_NAME:Marlin 2.1.2\nok\n"
        if command == "M122":
            return "\n".join(
                [
                    "Testing X connection... OK",
                    "Testing Y connection... Error: All LOW",
                    "Testing Z connection... Error: All LOW",
                    "Testing E connection... Error: All LOW",
                    "Testing E1 connection... Error: All LOW",
                    "ok",
                ]
            )
        return "ok\n"

    lines = iter(["CERRAR"])
    out = []
    code = serve(session, send, lambda _prompt: next(lines), out.append)
    assert code == 0
    assert not any(command.split()[0] in {"G0", "G1", "G28"} for command in sent)
    assert any("MOTOR X uart=OK" in line for line in out)
    assert any("Menú cerrado" in line for line in out)
    assert session.identity_ok is True
