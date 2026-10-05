"""Límites tomados de la documentación, no medidos en este banco."""

from __future__ import annotations

from tonf.model import Indicator

REFERENCE: tuple[Indicator, ...] = (
    Indicator(
        "mcu",
        "MCU",
        "referencia",
        "LPC1769, 120 MHz, 512 kB flash, 64 kB SRAM, cristal de 12 MHz",
        "Datasheet NXP. El PDF de BTT todavía dice LPC1768 a 100 MHz; el esquema vale para las dos.",
        "Compilar la Turbo como LPC1768 deja el reloj en 100 MHz. El core de Marlin limita la aplicación a unos 475 kB.",
    ),
    Indicator(
        "ejes",
        "Ejes en placa",
        "referencia",
        "5 zócalos: X, Y, Z, E0, E1",
        "ZBM va en paralelo con el driver Z. No es un sexto eje.",
        "Un eje más pide el módulo EXP-MOT o un driver externo en el header de lazo cerrado.",
    ),
    Indicator(
        "alimentacion",
        "Alimentación",
        "referencia",
        "DCIN 12–24 V; fusible VBB 10 A; USB 750 mA si 5V SEL está en USB",
        "5V SEL: USB|+5V habla con el MCU sin VMOT. +5V|VDD usa la fuente y el USB queda solo en datos.",
        "FAN1, FAN2 y FAN3 quedan a VBB en cuanto hay fuente. La cama, si se usa, queda en 144 W según el manual.",
    ),
    Indicator(
        "tmc2209",
        "TMC2209",
        "referencia",
        "UART propio por zócalo, dirección 0, sense 0,110 Ω en el módulo BTT",
        "VM de trabajo del circuito 5,5–29 V. Corriente de fábrica del módulo cerca de 0,85 A RMS.",
        "Sin módulo insertado no hay UART, corriente, StallGuard ni paso real que medir. El techo de micropasos del circuito ronda 6 MHz; el par cae antes, cuando la FEM se acerca a VM.",
    ),
    Indicator(
        "paso",
        "STEP/DIR",
        "referencia",
        "Un flanco de subida por micropaso. 3200 flancos = 1 vuelta a 16 micropasos en un motor de 1,8°",
        "Pines en la nota de hardware del 2026-10-05. Quien genera los pulsos es el Marlin instalado.",
        "El host de envío sigue esperando un banner grbl y no reenvía el archivo a este Marlin.",
    ),
    Indicator(
        "firmware",
        "Firmware",
        "referencia",
        "Marlin 2.0.5, medido por USB en COM3 el 2026-10-05",
        "M115: 3D Printer, 2 extrusores, EEPROM, protección térmica. Ejes X Y Z E E1. Pasos/mm X80 Y80 Z400 E96. Caja software 235 x 235 x 300 mm.",
        "Sin termistores las temperaturas leen -15 °C y un calentado corta la máquina. Sin finales reales los tres min leen TRIGGERED. M122 no ve TMC2209.",
    ),
)
