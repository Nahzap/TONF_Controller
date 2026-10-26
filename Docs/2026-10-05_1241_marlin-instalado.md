# Marlin instalado — alcances, límites e instrucciones — 2026-10-05 12:41

Lectura por USB de la BTT SKR V1.4 Turbo, sin motores ni módulos TMC2209 insertados. No se envió movimiento (`G0`, `G1`, `G28`), ni calor (`M104`, `M140`), ni grabación de EEPROM (`M500`).

Puerto: **COM3**, USB `1D50:6029`. Velocidad usada en esta pasada: **115200**. Cada línea termina en salto de línea. Abrir el COM reinicia la placa (DTR de Windows); hay que esperar un momento y luego preguntar.

## Identidad medida

`M115`:

```text
FIRMWARE_NAME:Marlin 2.0.5 (GitHub)
SOURCE_CODE_URL:https://github.com/MarlinFirmware/Marlin
PROTOCOL_VERSION:1.0
MACHINE_TYPE:3D Printer
EXTRUDER_COUNT:2
UUID:cede2a2f-41a2-4748-9b12-c55c62f367ff
```

Capacidades que el propio firmware declara (`Cap:`):

| Capacidad | Valor |
| --- | --- |
| EEPROM | sí |
| volumétrico | sí (en `M503` está apagado) |
| autoreporte de temperatura | sí |
| trabajo de impresión | sí |
| protección térmica | sí |
| XON/XOFF, transferencia binaria, progreso, autolevel, sonda Z, datos de nivelación, porcentaje de pieza, alimentación por software, luces, parser de emergencia, prompts, autoreporte de SD, modos de movimiento, cámara | no |

`M412` (sensor de filamento) respondió `Unknown command`. `M350` (micropasos por comando) también.

## Qué puede hacer este binario

Cinco canales de motor, con nombres de impresora:

| Canal | Letra / herramienta | Modo de driver compilado | Corriente configurada |
| --- | --- | --- | --- |
| X | `X` | stealthChop | 800 mA |
| Y | `Y` | stealthChop | 800 mA |
| Z | `Z` | stealthChop | 800 mA |
| E0 | extrusor `T0`, letra `E` | stealthChop | 800 mA |
| E1 | extrusor `T1` | spreadCycle | 800 mA |

Unidades: milímetros y grados Celsius (`G21`, `M149 C`).

Planificador, tal como lo devolvió `M503`:

| Parámetro | X | Y | Z | E |
| --- | --- | --- | --- | --- |
| Pasos por mm (`M92`) | 80 | 80 | 400 | 96 |
| Avance máximo (`M203`, mm/s) | 200 | 200 | 5 | 25 |
| Aceleración máxima (`M201`, mm/s²) | 1000 | 1000 | 100 | 10000 |

Aceleración de impresión, retracción y desplazamiento: 500 mm/s². Desviación de cruce: 0,01 mm. Tiempo mínimo de segmento: 20000 µs. Offset de home: cero. Offset del segundo hotend: cero. Salto de cambio de herramienta: Z 2,00 mm.

Caja de finales por software, encendida (`M211`):

- mínimo X0 Y0 Z0
- máximo X235 Y235 Z300

Esos 80 pasos/mm de X e Y coinciden con un motor de 1,8°, 16 micropasos y polea GT2 de 20 dientes. Los 400 pasos/mm de Z coinciden con un husillo de 8 mm por vuelta a 16 micropasos. En una mecánica distinta, el mismo `G1 X10` no recorre 10 mm.

La microSD responde. `M20` devolvió una lista vacía: la tarjeta está y no tiene archivos.

Hay EEPROM (`Cap:EEPROM:1`). `M503` lee lo que está activo. `M500` lo grabaría; no se envió.

## Límites medidos ahora

**No hay drivers en el UART.** `M122`:

```text
Testing X connection... Error: All HIGH
Testing Y connection... Error: All HIGH
Testing Z connection... Error: All HIGH
Testing E connection... Error: All HIGH
Testing E1 connection... Error: All LOW
```

`All HIGH` y `All LOW` son lecturas UART fallidas. Los 800 mA y stealthChop están escritos en el firmware; ningún TMC2209 los recibió en esta pasada. Sin módulo, el zócalo no mueve un eje.

**Los tres finales mínimos ya figuran accionados**, sin nada cableado:

```text
x_min: TRIGGERED
y_min: TRIGGERED
z_min: TRIGGERED
```

En esta placa el pin DIAG del TMC2209 va unido al final de ese eje. Con el zócalo vacío el pin queda en el estado que Marlin llama TRIGGERED. Un `G28` tomaría ese estado como tope. No se envió `G28`.

**No hay termistores.** `M105`:

```text
ok T:-15.00 /0.00 B:-15.00 /0.00 T0:-15.00 /0.00 T1:-15.00 /0.00 @:0 B@:0
```

−15 °C es la lectura de un ADC abierto. La protección térmica está compilada. Un `M104` o `M140` con la cama o el hotend en ese valor corta la máquina por temperatura mínima. Los dos hotends y la cama están en el firmware aunque no haya calentador conectado.

**El extrusor no se mueve en frío.** `M302`:

```text
echo:Cold extrudes are disabled (min temp 170C)
```

Cualquier `G1 E…` se rechaza mientras el hotend figure por debajo de 170 °C. Hoy figura a −15 °C, así que E y el segundo extrusor no avanzan. X, Y y Z no pasan por esa traba.

**La caja de impresora recorta el recorrido.** Con los finales por software activos, un destino fuera de 0…235 en X o Y, o fuera de 0…300 en Z, no se ejecuta. El origen reportado es `X:0 Y:0 Z:0 E:0` (`M114`).

**Este Marlin 2.0.5 no tiene ejes I, J, K, U, V ni W.** El quinto zócalo es el segundo extrusor, no un eje libre con su propia letra. Un sistema de ejes a medida tiene que mapearse a X, Y, Z y a los dos extrusores.

**Micropasos fijos.** `M350` no existe en este binario. La corriente (`M906`) y stealthChop/spreadCycle (`M569`) sí se pueden leer. Cambiar micropasos exige otro firmware o el potenciómetro del módulo, y el UART, cuando hay driver, pasa a mandar sobre el potenciómetro.

**Parser de emergencia apagado.** `M112` no corta un movimiento a media línea; Marlin 2.0.5 sin `EMERGENCY_PARSER` lo atiende al terminar el comando en curso.

**`tonf enviar` no habla con este firmware.** Ese comando espera un banner Grbl y no manda el archivo. El G-code de esta placa se escribe en un terminal serie a 115200.

## Instrucciones

Terminal serie en COM3, 115200, salto de línea. Tras abrir el puerto, esperar el reinicio y enviar:

```text
M115
M503
M114
M119
M105
M122
```

`M115` identifica. `M503` vuelca pasos, avances, aceleraciones, PID y corrientes. `M114` es la posición que el planificador cree, no un encoder. `M119` son los finales. `M105` son temperaturas. `M122` dice si el TMC2209 contesta.

Para un eje X o Y dentro de la caja, con un módulo ya instalado, UART en marcha y corriente revisada, el G-code de este Marlin es en milímetros absolutos:

```text
G90
G21
G1 X10 F600
```

`F600` son 600 mm/min (10 mm/s). El tope compilado de X es 200 mm/s. `G1 Z` no debería pasar de 5 mm/s (`F300`).

Estas consultas cambian estado; no se enviaron en la medición:

| Comando | Efecto |
| --- | --- |
| `M211 S0` | quita la caja 235 × 235 × 300 |
| `M211 S1` | la vuelve a poner |
| `M302 S0` | permite mover `E` con el hotend frío |
| `M92 X… Y… Z… E…` | cambia pasos/mm hasta apagar o hasta `M500` |
| `M500` | graba la EEPROM |
| `G28` | home; hoy los tres min ya están TRIGGERED |
| `M104` `M140` `M109` `M190` | calientan y, con −15 °C, disparan la protección |

Hasta que haya un TMC2209 alimentado en VM y visible en `M122`, un `G1` solo produce flancos en el pin STEP. No hay eje físico.
