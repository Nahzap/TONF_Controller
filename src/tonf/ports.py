"""Inventario de puertos serie y elección de la SKR, sin abrirlos todavía."""

from __future__ import annotations

from dataclasses import dataclass

# USB VID que usan el bootloader Smoothie y varios firmware LPC (Marlin, Klipper).
_HINT_VIDS = {0x1D50}
_HINT_TEXT = ("klipper", "marlin", "smoothie", "skr", "lpc176")


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str
    hwid: str
    vid: int | None
    pid: int | None
    manufacturer: str
    product: str

    @property
    def blob(self) -> str:
        return " ".join(
            part
            for part in (
                self.device,
                self.description,
                self.hwid,
                self.manufacturer,
                self.product,
            )
            if part
        ).lower()

    @property
    def usb(self) -> bool:
        return self.vid is not None

    @property
    def hint(self) -> bool:
        if self.vid in _HINT_VIDS:
            return True
        return any(token in self.blob for token in _HINT_TEXT)


def from_list_port(raw: object) -> PortInfo:
    return PortInfo(
        device=str(getattr(raw, "device", "")),
        description=str(getattr(raw, "description", "") or ""),
        hwid=str(getattr(raw, "hwid", "") or ""),
        vid=getattr(raw, "vid", None),
        pid=getattr(raw, "pid", None),
        manufacturer=str(getattr(raw, "manufacturer", "") or ""),
        product=str(getattr(raw, "product", "") or ""),
    )


def selectable(ports: list[PortInfo], requested: str | None) -> tuple[list[PortInfo], str]:
    """Devuelve los puertos que se pueden abrir y el motivo.

    Con varios USB serie genéricos no se abre ninguno: en Windows el
    alta del puerto reinicia muchas placas, y no hay que tocar un
    dispositivo que no sea la SKR.
    """

    if requested:
        match = [port for port in ports if port.device.upper() == requested.upper()]
        if not match:
            return [], f"No existe el puerto {requested}."
        return match, f"Puerto pedido: {requested}."

    usb = [port for port in ports if port.usb and "bluetooth" not in port.blob]
    hinted = [port for port in usb if port.hint]
    if len(hinted) == 1:
        return hinted, "Un solo USB serie coincide con LPC/Marlin/Klipper."
    if len(hinted) > 1:
        names = ", ".join(port.device for port in hinted)
        return [], f"Varios candidatos ({names}). Repite con --port."
    if len(usb) == 1:
        return usb, "Un solo USB serie en el sistema; se prueba ese."
    if len(usb) > 1:
        names = ", ".join(port.device for port in usb)
        return [], f"Hay varios USB serie ({names}) y ninguno se identifica como la SKR. Repite con --port."
    return [], "No hay un USB serie. Revisa el cable, el jumper 5V SEL (USB con +5V) y que D5 esté encendido."
