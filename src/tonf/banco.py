"""Carga config/banco.toml y arma la suite de motores.

La suite aplica corriente, avance máximo, pasos/mm, stealthChop y los
movimientos de cada canal. No homea y no enciende calentadores.
"""

from __future__ import annotations

import time
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path


class ConfigError(ValueError):
    """El archivo de señales no se puede ejecutar."""


@dataclass(frozen=True)
class Move:
    distancia_mm: float
    avance_mm_min: float
    espera_comando_s: float
    espera_fin_s: float


@dataclass(frozen=True)
class Channel:
    id: str
    orden: int
    activo: bool
    secuencia: str
    modelo: str
    nota: str
    letra: str
    herramienta: int | None
    corriente_ma: int
    corriente_nominal_ma: int | None
    pasos_por_mm: float
    micropasos: int
    grados_por_paso: float
    sentido: int
    sigilo: bool
    dir_invertido_compilado: bool
    driver: str
    uart_direccion: int
    rsense_modulo_ohm: float
    rsense_compilado_ohm: float
    interpolar: bool
    step: str
    dir: str
    enable: str
    uart: str
    diag: str
    origen_mm: float | None


@dataclass(frozen=True)
class Bench:
    path: Path
    puerto: str
    baud: int
    espera_apertura_s: float
    vmot_v: float
    logica: str
    techo_ma: int
    home: bool
    calentar: bool
    nombre: str
    firmware: str
    placa: str
    mcu: str
    guardar_eeprom: bool
    extrusion_en_frio: bool
    extrusion_min_c: int
    extrusion_max_mm: float
    sensor_filamento: bool
    origen_mm: float
    retencion: float
    chopper: str
    enable_activo_bajo: bool
    plug: str
    soltar_al_final: bool
    herramienta_al_final: int
    avances_mm_s: dict[str, float]
    limites_mm: dict[str, tuple[float, float]]
    consulta_s: float
    guardar_s: float
    driver_s: float
    secuencias: dict[str, tuple[Move, ...]]
    channels: tuple[Channel, ...]

    def ordered(self) -> tuple[Channel, ...]:
        return tuple(sorted(self.channels, key=lambda channel: channel.orden))


@dataclass(frozen=True)
class Step:
    command: str
    timeout_s: float
    group: str


@dataclass(frozen=True)
class Program:
    steps: tuple[Step, ...]
    warnings: tuple[str, ...]


_CARTESIAN = frozenset({"X", "Y", "Z"})
_FORBIDDEN = ("G28", "M104", "M109", "M140", "M190")


def config_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        path = explicit
    else:
        path = None
        cwd = Path.cwd()
        for folder in (cwd, *cwd.parents):
            candidate = folder / "config" / "banco.toml"
            if candidate.is_file():
                path = candidate
                break
        if path is None:
            path = Path(__file__).resolve().parents[2] / "config" / "banco.toml"
    if not path.is_file():
        raise ConfigError(f"No está el archivo de configuración {path}.")
    return path


def load_path(path: Path | None = None) -> Bench:
    file = config_path(path)
    return load_text(file.read_text(encoding="utf-8"), file)


def load_text(text: str, path: Path | None = None) -> Bench:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"El archivo de configuración no es TOML válido: {exc}") from exc
    return _bench(raw, path or Path("config/banco.toml"))


def build(bench: Bench, only: str | None = None) -> Program:
    _require_safe(bench)
    channels = bench.ordered()
    _require_currents(bench, channels)
    _require_shared_extruder_steps(channels)
    moving = _select(channels, only)
    warnings = _warnings(bench, channels, moving)
    steps: list[Step] = []
    steps.extend(_setup(bench, channels))
    for channel in moving:
        steps.extend(_channel_steps(bench, channel))
    steps.extend(_closing(bench))
    _reject_forbidden(steps)
    return Program(tuple(steps), tuple(warnings))


def describe(bench: Bench, only: str | None = None) -> str:
    program = build(bench, only)
    moving = {channel.id for channel in _select(bench.ordered(), only)}
    lines = [
        f"Configuración: {bench.path}",
        f"{bench.nombre}  {bench.firmware}  {bench.placa}  {bench.mcu}",
        f"Enlace: {bench.puerto} a {bench.baud} baudios",
        f"Alimentación: {bench.vmot_v:g} V en VMOT, lógica {bench.logica}",
        f"Techo de corriente: {bench.techo_ma} mA",
        f"Plug de motor: {bench.plug}",
        f"Retención compilada: {bench.retencion:g} de la corriente de marcha",
        f"Chopper compilado: {bench.chopper}",
        f"ENABLE activo en bajo: {'sí' if bench.enable_activo_bajo else 'no'}",
        "",
    ]
    for channel in bench.ordered():
        mark = "se mueve" if channel.id in moving else "sin movimiento"
        if not channel.activo:
            mark = "inactivo"
        lines.append(f"Canal {channel.id}  orden {channel.orden}  {mark}")
        lines.append(f"  Motor: {channel.modelo}")
        if channel.nota:
            lines.append(f"  Nota: {channel.nota}")
        nominal = (
            f"  nominal {channel.corriente_nominal_ma} mA"
            if channel.corriente_nominal_ma is not None
            else ""
        )
        lines.append(f"  Corriente: {channel.corriente_ma} mA{nominal}")
        lines.append(
            f"  Pasos/mm: {_num(channel.pasos_por_mm)}   "
            f"Micropasos compilados: {channel.micropasos}   "
            f"Grados/paso: {_num(channel.grados_por_paso)}"
        )
        lines.append(
            f"  Sentido de la prueba: {channel.sentido:+d}   "
            f"StealthChop: {'sí' if channel.sigilo else 'no'}   "
            f"DIR compilado: {'invertido' if channel.dir_invertido_compilado else 'directo'}"
        )
        if channel.herramienta is not None:
            lines.append(f"  Herramienta Marlin: T{channel.herramienta}  letra {channel.letra}")
        lines.append(
            f"  Driver {channel.driver}  UART {channel.uart_direccion}  "
            f"Rsense módulo {_num(channel.rsense_modulo_ohm)} Ω  "
            f"Rsense compilado {_num(channel.rsense_compilado_ohm)} Ω  "
            f"Interpolación: {'sí' if channel.interpolar else 'no'}"
        )
        lines.append(
            f"  STEP {channel.step}  DIR {channel.dir}  EN {channel.enable}  "
            f"UART {channel.uart}  DIAG {channel.diag}"
        )
        lines.append(f"  Secuencia: {channel.secuencia}")
        for move in bench.secuencias[channel.secuencia]:
            signed = channel.sentido * move.distancia_mm
            turns = shaft_turns(channel, move.distancia_mm)
            lines.append(
                f"    {_num(signed)} mm a {_num(move.avance_mm_min)} mm/min"
                f"  ({turns:.2f} vueltas)"
            )
        lines.append("")
    if program.warnings:
        lines.append("Avisos:")
        lines.extend(f"  - {warning}" for warning in program.warnings)
    return "\n".join(lines).rstrip()


def format_program(program: Program) -> str:
    lines = [f"# {warning}" for warning in program.warnings]
    group = ""
    for step in program.steps:
        if step.group != group:
            group = step.group
            lines.append(f"\n# --- {group} ---")
        lines.append(step.command)
    return "\n".join(lines).strip()


def shaft_turns(channel: Channel, distancia_mm: float) -> float:
    steps_per_rev = (360.0 / channel.grados_por_paso) * channel.micropasos
    return abs(distancia_mm) * channel.pasos_por_mm / steps_per_rev


def execute(port, steps: tuple[Step, ...] | list[Step], settle_s: float = 0.05) -> int:
    """Manda la lista. Devuelve 0 si toda la lista fue aceptada."""
    failed = False
    for step in steps:
        print(f"\n===== {step.group}: {step.command} =====")
        body = transact(port, step.command, step.timeout_s, settle_s)
        print(body or "(sin respuesta)")
        if _rejected(body):
            print("DETENIDO")
            failed = True
            break
    if failed:
        print("\n===== cierre: M18 =====")
        print(transact(port, "M18", 3, settle_s) or "(sin respuesta)")
    return 1 if failed else 0


def run(bench: Bench, only: str | None = None) -> int:
    program = build(bench, only)
    for warning in program.warnings:
        print(f"Aviso: {warning}")
    port = open_port(bench.puerto, bench.baud, bench.espera_apertura_s)
    try:
        return execute(port, program.steps)
    finally:
        port.close()


def open_port(puerto: str, baud: int, espera_s: float):
    import serial

    port = serial.Serial(puerto, baud, timeout=0.3, write_timeout=2)
    time.sleep(espera_s)
    port.reset_input_buffer()
    return port


def transact(port, command: str, timeout_s: float, settle_s: float = 0.05) -> str:
    port.write((command + "\n").encode("ascii"))
    port.flush()
    end = time.time() + timeout_s
    chunks: list[bytes] = []
    while time.time() < end:
        block = port.read(4096)
        if not block:
            text = b"".join(chunks).decode("utf-8", "replace").replace("\r", "")
            if _accepted(text):
                break
            continue
        chunks.append(block)
        text = b"".join(chunks).decode("utf-8", "replace").replace("\r", "")
        if _accepted(text):
            if settle_s:
                time.sleep(settle_s)
            extra = port.read(4096)
            if extra:
                chunks.append(extra)
            break
    return b"".join(chunks).decode("utf-8", "replace").replace("\r", "").strip()


def replace_channel(bench: Bench, channel_id: str, **changes) -> Bench:
    found = False
    channels = []
    for channel in bench.channels:
        if channel.id == channel_id:
            channels.append(replace(channel, **changes))
            found = True
        else:
            channels.append(channel)
    if not found:
        raise ConfigError(f"No existe el canal {channel_id}.")
    return replace(bench, channels=tuple(channels))


def _bench(raw: dict, path: Path) -> Bench:
    link = _table(raw, "enlace")
    power = _table(raw, "alimentacion")
    safety = _table(raw, "seguridad")
    machine = _table(raw, "maquina")
    feeds = _table(raw, "avances_maximos_mm_s")
    limits = _table(raw, "limites_mm")
    times = _table(raw, "tiempos")
    sequences = _sequences(_table(raw, "secuencia"))
    channels = _channels(_table(raw, "canales"), sequences)
    bench = Bench(
        path=path,
        puerto=_text(link, "puerto"),
        baud=_int(link, "baud", minimum=1),
        espera_apertura_s=_float(link, "espera_apertura_s", minimum=0),
        vmot_v=_float(power, "vmot_v", minimum=0),
        logica=_text(power, "logica"),
        techo_ma=_int(power, "techo_ma", minimum=1),
        home=_bool(safety, "home"),
        calentar=_bool(safety, "calentar"),
        nombre=_text(machine, "nombre"),
        firmware=_text(machine, "firmware"),
        placa=_text(machine, "placa"),
        mcu=_text(machine, "mcu"),
        guardar_eeprom=_bool(machine, "guardar_eeprom"),
        extrusion_en_frio=_bool(machine, "extrusion_en_frio"),
        extrusion_min_c=_int(machine, "extrusion_min_c", minimum=0),
        extrusion_max_mm=_float(machine, "extrusion_max_mm", minimum=0),
        sensor_filamento=_bool(machine, "sensor_filamento"),
        origen_mm=_float(machine, "origen_mm"),
        retencion=_float(machine, "retencion", minimum=0),
        chopper=_text(machine, "chopper"),
        enable_activo_bajo=_bool(machine, "enable_activo_bajo"),
        plug=_text(machine, "plug"),
        soltar_al_final=_bool(machine, "soltar_al_final"),
        herramienta_al_final=_int(machine, "herramienta_al_final", minimum=-1),
        avances_mm_s={axis: _float(feeds, axis, minimum=0) for axis in ("X", "Y", "Z", "E")},
        limites_mm={axis: _span(limits, axis) for axis in ("X", "Y", "Z")},
        consulta_s=_float(times, "consulta_s", minimum=0.1),
        guardar_s=_float(times, "guardar_s", minimum=0.1),
        driver_s=_float(times, "driver_s", minimum=0.1),
        secuencias=sequences,
        channels=channels,
    )
    _require_safe(bench)
    _require_currents(bench, bench.ordered())
    _require_shared_extruder_steps(bench.ordered())
    return bench


def _sequences(raw: dict) -> dict[str, tuple[Move, ...]]:
    if not raw:
        raise ConfigError("Falta [secuencia] con al menos un patrón de movimiento.")
    sequences: dict[str, tuple[Move, ...]] = {}
    for name, body in raw.items():
        if not isinstance(body, dict) or "movimientos" not in body:
            raise ConfigError(f"La secuencia {name} no tiene [[secuencia.{name}.movimientos]].")
        moves = []
        for index, item in enumerate(body["movimientos"], start=1):
            if not isinstance(item, dict):
                raise ConfigError(f"El movimiento {index} de {name} está mal escrito.")
            distance = _float(item, "distancia_mm")
            if distance == 0:
                raise ConfigError(f"El movimiento {index} de {name} tiene distancia 0.")
            moves.append(
                Move(
                    distancia_mm=distance,
                    avance_mm_min=_float(item, "avance_mm_min", minimum=0.1),
                    espera_comando_s=_float(item, "espera_comando_s", minimum=0.1),
                    espera_fin_s=_float(item, "espera_fin_s", minimum=0.1),
                )
            )
        if not moves:
            raise ConfigError(f"La secuencia {name} no tiene movimientos.")
        sequences[name] = tuple(moves)
    return sequences


def _channels(raw: dict, sequences: dict[str, tuple[Move, ...]]) -> tuple[Channel, ...]:
    if not raw:
        raise ConfigError("Falta [canales] con X, Y, Z, E0 y E1.")
    channels = []
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise ConfigError(f"El canal {name} está mal escrito.")
        letter = _text(body, "letra")
        if letter not in {"X", "Y", "Z", "E"}:
            raise ConfigError(f"{name}: letra tiene que ser X, Y, Z o E.")
        tool = body.get("herramienta")
        if letter == "E":
            if tool is None:
                raise ConfigError(f"{name}: un extrusor necesita herramienta (0 para E0, 1 para E1).")
            tool = _int(body, "herramienta", minimum=0)
        elif tool is not None:
            raise ConfigError(f"{name}: un eje cartesiano no lleva herramienta.")
        else:
            tool = None
        if name in _CARTESIAN and letter != name:
            raise ConfigError(f"{name}: la letra tiene que ser {name}.")
        if name == "E0" and tool != 0:
            raise ConfigError("E0 tiene que usar herramienta = 0.")
        if name == "E1" and tool != 1:
            raise ConfigError("E1 tiene que usar herramienta = 1.")
        sequence = _text(body, "secuencia")
        if sequence not in sequences:
            raise ConfigError(f"{name} apunta a la secuencia {sequence}, y esa secuencia no existe.")
        direction = _int(body, "sentido")
        if direction not in (1, -1):
            raise ConfigError(f"{name}: sentido tiene que ser 1 o -1.")
        nominal = body.get("corriente_nominal_ma")
        channels.append(
            Channel(
                id=name,
                orden=_int(body, "orden", minimum=1),
                activo=_bool(body, "activo"),
                secuencia=sequence,
                modelo=_text(body, "modelo"),
                nota=str(body.get("nota", "")),
                letra=letter,
                herramienta=tool,
                corriente_ma=_int(body, "corriente_ma", minimum=1),
                corriente_nominal_ma=None if nominal is None else _int(body, "corriente_nominal_ma", minimum=1),
                pasos_por_mm=_float(body, "pasos_por_mm", minimum=0.1),
                micropasos=_int(body, "micropasos", minimum=1),
                grados_por_paso=_float(body, "grados_por_paso", minimum=0.1),
                sentido=direction,
                sigilo=_bool(body, "sigilo"),
                dir_invertido_compilado=_bool(body, "dir_invertido_compilado"),
                driver=_text(body, "driver"),
                uart_direccion=_int(body, "uart_direccion", minimum=0),
                rsense_modulo_ohm=_float(body, "rsense_modulo_ohm", minimum=0),
                rsense_compilado_ohm=_float(body, "rsense_compilado_ohm", minimum=0),
                interpolar=_bool(body, "interpolar"),
                step=_text(body, "step"),
                dir=_text(body, "dir"),
                enable=_text(body, "enable"),
                uart=_text(body, "uart"),
                diag=_text(body, "diag"),
                origen_mm=None if "origen_mm" not in body else _float(body, "origen_mm"),
            )
        )
    orders = [channel.orden for channel in channels]
    if len(orders) != len(set(orders)):
        raise ConfigError("Hay dos canales con el mismo orden.")
    return tuple(channels)


def _setup(bench: Bench, channels: tuple[Channel, ...]) -> list[Step]:
    cold = "M302 S0" if bench.extrusion_en_frio else f"M302 S{bench.extrusion_min_c}"
    filament = "M412 S1" if bench.sensor_filamento else "M412 S0"
    feeds = " ".join(f"{axis}{_num(bench.avances_mm_s[axis])}" for axis in ("X", "Y", "Z", "E"))
    steps = [
        Step("M114", bench.consulta_s, "ajuste"),
        Step(cold, bench.consulta_s, "ajuste"),
        Step(filament, bench.consulta_s, "ajuste"),
        Step(f"M203 {feeds}", bench.consulta_s, "ajuste"),
    ]
    steps.extend(Step(_m906(channel), bench.consulta_s, "ajuste") for channel in channels)
    steps.extend(Step(_m569(channel), bench.consulta_s, "ajuste") for channel in channels)
    steps.append(Step(_m92(channels), bench.consulta_s, "ajuste"))
    if bench.guardar_eeprom:
        steps.append(Step("M500", bench.guardar_s, "ajuste"))
    steps.extend(
        (
            Step("M906", bench.consulta_s, "ajuste"),
            Step("M92", bench.consulta_s, "ajuste"),
            Step("M569", bench.driver_s, "ajuste"),
        )
    )
    return steps


def _channel_steps(bench: Bench, channel: Channel) -> list[Step]:
    origin = bench.origen_mm if channel.origen_mm is None else channel.origen_mm
    _require_travel(bench, channel, origin)
    group = channel.id
    steps: list[Step] = []
    if channel.herramienta is not None:
        steps.append(Step(f"T{channel.herramienta}", bench.consulta_s, group))
    if channel.letra == "E":
        steps.append(Step("M83", bench.consulta_s, group))
        steps.append(Step(f"G92 E{_num(origin)}", bench.consulta_s, group))
    else:
        steps.extend(
            (
                Step("G90", bench.consulta_s, group),
                Step(f"G92 {channel.letra}{_num(origin)}", bench.consulta_s, group),
                Step("G91", bench.consulta_s, group),
            )
        )
    for move in bench.secuencias[channel.secuencia]:
        signed = channel.sentido * move.distancia_mm
        command = f"G1 {channel.letra}{_num(signed)} F{_num(move.avance_mm_min)}"
        steps.append(Step(command, move.espera_comando_s, group))
        steps.append(Step("M400", move.espera_fin_s, group))
    steps.extend(
        (
            Step("M114", bench.consulta_s, group),
            Step("M122", bench.driver_s, group),
            Step("M119", bench.consulta_s, group),
        )
    )
    return steps


def _closing(bench: Bench) -> list[Step]:
    steps = [Step("G90", bench.consulta_s, "cierre")]
    if bench.herramienta_al_final >= 0:
        steps.append(Step(f"T{bench.herramienta_al_final}", bench.consulta_s, "cierre"))
    if bench.soltar_al_final:
        steps.append(Step("M18", bench.consulta_s, "cierre"))
    return steps


def _require_safe(bench: Bench) -> None:
    if bench.home:
        raise ConfigError("Esta suite no homea. seguridad.home tiene que quedar en false.")
    if bench.calentar:
        raise ConfigError(
            "Esta suite no enciende calentadores. seguridad.calentar tiene que quedar en false."
        )


def _require_currents(bench: Bench, channels: tuple[Channel, ...]) -> None:
    for channel in channels:
        if channel.corriente_ma > bench.techo_ma:
            raise ConfigError(
                f"{channel.id} pide {channel.corriente_ma} mA y el techo es {bench.techo_ma} mA."
            )


def _require_shared_extruder_steps(channels: tuple[Channel, ...]) -> None:
    values = {channel.pasos_por_mm for channel in channels if channel.letra == "E"}
    if len(values) > 1:
        raise ConfigError(
            "E0 y E1 tienen pasos/mm distintos. Este firmware no compila DISTINCT_E_FACTORS, "
            "así que M92 E escribe los dos a la vez. Iguala pasos_por_mm, o recompila con esa opción."
        )


def _require_travel(bench: Bench, channel: Channel, origin: float) -> None:
    if channel.letra == "E":
        for move in bench.secuencias[channel.secuencia]:
            if abs(move.distancia_mm) > bench.extrusion_max_mm:
                raise ConfigError(
                    f"{channel.id}: un tramo de {abs(move.distancia_mm):g} mm pasa "
                    f"el máximo de extrusión ({bench.extrusion_max_mm:g} mm)."
                )
        return
    low, high = bench.limites_mm[channel.letra]
    if not low <= origin <= high:
        raise ConfigError(
            f"{channel.id}: el origen {_num(origin)} mm está fuera de {_num(low)}…{_num(high)} mm."
        )
    position = origin
    for move in bench.secuencias[channel.secuencia]:
        position += channel.sentido * move.distancia_mm
        if position < low or position > high:
            raise ConfigError(
                f"{channel.id}: el movimiento deja el eje en {_num(position)} mm, "
                f"fuera de {_num(low)}…{_num(high)} mm."
            )


def _select(channels: tuple[Channel, ...], only: str | None) -> tuple[Channel, ...]:
    if only is None:
        chosen = tuple(channel for channel in channels if channel.activo)
        if not chosen:
            raise ConfigError("No hay canales activos.")
        return chosen
    key = only.upper()
    match = [channel for channel in channels if channel.id.upper() == key]
    if not match:
        names = ", ".join(channel.id for channel in channels)
        raise ConfigError(f"No existe el canal {only}. Canales: {names}.")
    if not match[0].activo:
        raise ConfigError(f"{match[0].id} está con activo = false.")
    return (match[0],)


def _warnings(bench: Bench, channels: tuple[Channel, ...], moving: tuple[Channel, ...]) -> list[str]:
    warnings = []
    for channel in channels:
        if channel.corriente_nominal_ma is not None and channel.corriente_ma > channel.corriente_nominal_ma:
            warnings.append(
                f"{channel.id} pide {channel.corriente_ma} mA y la nominal del motor es "
                f"{channel.corriente_nominal_ma} mA."
            )
        if abs(channel.rsense_compilado_ohm - channel.rsense_modulo_ohm) > 0.001:
            warnings.append(
                f"{channel.id}: el firmware tiene Rsense {_num(channel.rsense_compilado_ohm)} Ω "
                f"y el módulo es {_num(channel.rsense_modulo_ohm)} Ω. "
                "El mA de M906 no es la corriente real de bobina hasta corregir el firmware."
            )
        if channel.micropasos != 16 or not channel.interpolar:
            warnings.append(
                f"{channel.id}: micropasos {channel.micropasos} e interpolar "
                f"{'sí' if channel.interpolar else 'no'} están solo en el archivo. "
                "La suite no los reprograma; el firmware compilado usa 16 micropasos con interpolación."
            )
    for channel in moving:
        limit = bench.avances_mm_s[channel.letra]
        for move in bench.secuencias[channel.secuencia]:
            feed = move.avance_mm_min / 60.0
            if feed > limit:
                warnings.append(
                    f"{channel.id}: un tramo pide {_num(feed)} mm/s y M203 de {channel.letra} "
                    f"está en {_num(limit)} mm/s. Marlin recorta ese avance."
                )
                break
    return warnings


def _reject_forbidden(steps: list[Step]) -> None:
    for step in steps:
        head = step.command.split()[0].upper()
        if head in _FORBIDDEN:
            raise ConfigError(f"La suite no puede enviar {head}.")


def _m906(channel: Channel) -> str:
    if channel.letra == "E":
        return f"M906 T{channel.herramienta} E{channel.corriente_ma}"
    return f"M906 {channel.letra}{channel.corriente_ma}"


def _m569(channel: Channel) -> str:
    bit = 1 if channel.sigilo else 0
    if channel.letra == "E":
        return f"M569 T{channel.herramienta} E S{bit}"
    return f"M569 {channel.letra} S{bit}"


def _m92(channels: tuple[Channel, ...]) -> str:
    values: dict[str, float] = {}
    for channel in channels:
        values[channel.letra] = channel.pasos_por_mm
    return "M92 " + " ".join(f"{axis}{_num(values[axis])}" for axis in ("X", "Y", "Z", "E") if axis in values)


def _accepted(text: str) -> bool:
    return any(line == "ok" or line.startswith("ok ") for line in text.splitlines())


def _rejected(body: str) -> bool:
    lowered = body.lower()
    return (
        "unknown command" in lowered
        or "cold extrusion" in lowered
        or "invalid extruder" in lowered
        or body.startswith("Error")
    )


def _table(raw: dict, name: str) -> dict:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"Falta la tabla [{name}].")
    return value


def _text(table: dict, key: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Falta {key}.")
    return value.strip()


def _bool(table: dict, key: str) -> bool:
    value = table.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} tiene que ser true o false.")
    return value


def _int(table: dict, key: str, minimum: int | None = None) -> int:
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} tiene que ser un entero.")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{key} tiene que ser al menos {minimum}.")
    return value


def _float(table: dict, key: str, minimum: float | None = None) -> float:
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} tiene que ser un número.")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ConfigError(f"{key} tiene que ser al menos {minimum}.")
    return number


def _span(table: dict, key: str) -> tuple[float, float]:
    value = table.get(key)
    if not isinstance(value, list) or len(value) != 2:
        raise ConfigError(f"limites_mm.{key} tiene que ser [mínimo, máximo].")
    low, high = float(value[0]), float(value[1])
    if low >= high:
        raise ConfigError(f"limites_mm.{key}: el mínimo tiene que ser menor que el máximo.")
    return low, high


def _num(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")
