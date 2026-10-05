# TONF Controller

Banco de cinco motores sobre una BigTreeTech SKR V1.4 Turbo. El programa de este repositorio habla con la placa por USB, escribe las señales de cada canal y recorre los motores en vacío. No es un host de impresora 3D.

La placa que está medida corre Marlin 2.1.2, máquina «TONF SKR», compilado el 5 de octubre de 2026 a las 16:39, con dos extrusores. Los cinco zócalos llevan módulos TMC2209 en UART. El archivo que se edita para cambiar corrientes, avances, sentidos y recorridos es `config/banco.toml`. La pasada de los cinco canales es `scripts/suite.py`. Cada canal también tiene su programa propio en `scripts/`, y una copia de esos cinco programas está en `BKP/`.

Repositorio: https://github.com/Nahzap/TONF_Controller.git

Este README es el documento de operación. Las notas de trabajo que viven en `Docs/` no forman parte del repositorio.

## Qué hay que tener conectado

| Pieza | Dato de este banco |
|---|---|
| Placa | BTT SKR V1.4 Turbo, MCU NXP LPC1769 a 120 MHz |
| Drivers | Cinco TMC2209 BTT, uno por zócalo, UART de un hilo, dirección 0 |
| Fuente de motores | 12 V en el bornero DCIN. La placa admite 12–24 V |
| Lógica | Puente 5V SEL entre +5V y VDD. El USB solo lleva datos |
| Enlace | USB-B, puerto COM3, 115200 baudios, salto de línea |
| Motores | X, Y, Z, E0 y E1. E0 y E1 son el cuarto y el quinto eje, no un extrusor de filamento |

ZBM, el segundo bornero de Z, va en paralelo con el driver Z. No es un sexto eje. El header de seis pines que hay junto a cada eje (STEP, DIR, EN, 3,3 V, GND, VBB) es para un driver externo de lazo cerrado, no para otro motor.

No se inserta ni se retira un módulo TMC2209 con la fuente puesta. La orientación del módulo sigue el serigrafiado: EN y VMOT hacia los bornes del motor, DIR y GND hacia el MCU. Un módulo al revés quema el driver.

El orden del plug del motor, del lado del zócalo, es `1B 1A 2A 2B`.

### Puente 5V SEL

El jumper J15 tiene tres pines, de izquierda a derecha: USB, +5V, VDD.

- USB unido a +5V: la lógica sale del PC. Sirve para hablar con el MCU. VMOT sigue apagado y los drivers no contestan por UART.
- +5V unido a VDD: la lógica sale de la fuente de 12 V. Es la posición para mover motores. El USB queda solo en datos.
- USB puesto, puente en +5V–VDD y fuente apagada: el MCU no arranca.

FAN1, FAN2 y FAN3 quedan a la tensión de la fuente en cuanto hay 12 V. No los apaga el firmware.

### Jumpers de cada TMC2209

Un solo puente por zócalo, en el par UART / MS3 (el recuadro que queda junto a los bornes del motor). MS1, MS2 y los cuatro puentes SPI van sin jumper. MS1 o MS2 cambian la dirección UART y el módulo deja de contestar en la dirección 0.

En los módulos BTT el pin PDN ya está unido al header. No hay que soldar nada en el módulo. DIAG del módulo entra en el zócalo: ese pin es el mismo que el final de carrera del eje. Un final mecánico exigiría sacar DIAG. Esta suite no usa finales mecánicos ni hace home.

ENABLE es activo en bajo. Un nivel alto en ENN apaga el puente del driver.

## Árbol

```text
README.md                  este documento
pyproject.toml             paquete Python tonf-controller
config/banco.toml          señales de los cinco canales
scripts/suite.py           prueba unificada, orden X Y Z E0 E1
scripts/prueba_motor_*.py  prueba de un canal. Son los programas base
BKP/                       copia de esos cinco programas base
src/tonf/                  programa: enlace, medidas y la suite
tests/                     pruebas del programa, sin abrir la placa
```

No entran al repositorio la carpeta `Docs/`, el entorno `.venv/`, la caché de pytest, los informes de `reports/` ni el fuente de Marlin de `firmware/`. El firmware grabado en la placa se describe más abajo. El árbol de Marlin, cuando hace falta recompilar, está solo en la máquina de trabajo.

## Motores y corrientes

`corriente_ma` en el archivo de configuración es la corriente RMS que Marlin escribe con `M906`. El techo de protección del banco es 800 mA. La suite no arranca si algún canal lo pasa.

| Canal | Motor | Corriente de la suite | Nominal de catálogo | Pasos/mm | DIR compilado |
|---|---|---|---|---|---|
| X | Sin nombre de catálogo | 450 mA | — | 80 | invertido |
| Y | CF3925-100-SL | 800 mA | no hay ficha | 80 | invertido |
| Z | SY42STH38-1684A | 800 mA | 1680 mA por fase | 400 | directo |
| E0 | SY42STH38-1684A | 800 mA | 1680 mA por fase | 95 | invertido |
| E1 | CF3925-100-SL | 800 mA | no hay ficha | 95 | directo |

X se dejó en 450 mA porque en el banco ese motor se movió entre 400 y 500 mA. Y, Z, E0 y E1 están en el tope de 800 mA. Z y E0 se nombraron en el banco como SY52STH38 1684A; el catálogo de 1,68 A por fase es el SY42STH38-1684A. Del CF3925-100-SL no hay corriente de fabricante en este banco. El cálculo de vueltas de ese modelo supone 1,8 ° por paso.

E0 es la herramienta T0 y E1 es la herramienta T1. Los dos se mueven con la letra E de G-code. `M906 E800` sin índice, en este Marlin, escribe los dos extrusores a la vez. La suite manda `M906 T0 E…` y `M906 T1 E…`.

### Resistencia de sensado

El módulo BTT mide 0,11 Ω. El firmware compilado no usa ese valor en todos los canales, y la suite no puede cambiarlo por el puerto. Mientras no coincidan, el número de `M906` no es la corriente real de la bobina. La suite lo avisa en cada corrida.

| Canal | Rsense compilada | Rsense del módulo |
|---|---|---|
| X | 0,0 Ω | 0,11 Ω |
| Y | 0,062 Ω | 0,11 Ω |
| Z | 0,062 Ω | 0,11 Ω |
| E0 | 0,062 Ω | 0,11 Ω |
| E1 | 0,11 Ω | 0,11 Ω |

E1 es el único canal en el que los dos valores coinciden. Con 800 mA de consigna, Marlin reportó 795 mA RMS. En Y, Z y E0, la misma consigna de 800 mA se reporta como 776 mA, calculada con la Rsense del fuente. En X, 450 mA se reporta como 397 mA.

Corregir la Rsense es editar `X_RSENSE`, `Y_RSENSE`, `Z_RSENSE` y `E0_RSENSE` en `Configuration_adv.h` del fuente local y grabar otro `firmware.bin`.

La corriente de reposo es la mitad de la de marcha (`HOLD_MULTIPLIER` 0,5). En X, con 450 mA, esa mitad cae a un escalón que el driver muestra como corriente de retención 0. No es una bobina abierta.

### Pines

| Canal | STEP | DIR | ENABLE | UART | DIAG |
|---|---|---|---|---|---|
| X | P2.02 | P2.06 | P2.01 | P1.10 | P1.29, X-STOP |
| Y | P0.19 | P0.20 | P2.08 | P1.09 | P1.28, Y-STOP |
| Z | P0.22 | P2.11 | P0.21 | P1.08 | P1.27, Z-STOP |
| E0 | P2.13 | P0.11 | P2.12 | P1.04 | P1.26, E0DET |
| E1 | P1.15 | P1.14 | P1.16 | P1.01 | P1.25, E1DET |

Esos nombres también están en cada canal de `config/banco.toml`. Cambiarlos ahí no recoloca un pin: el mapa está compilado en Marlin.

## Firmware que corre la placa

Marlin 2.1.2, `MACHINE_TYPE` «TONF SKR», `EXTRUDER_COUNT` 2, USB en `SERIAL_PORT -1` a 115200. Identidad con `M115`.

| Parámetro compilado | Valor |
|---|---|
| Drivers | TMC2209 en X, Y, Z, E0 y E1 |
| Micropasos | 16, con interpolación a 256 |
| Chopper | `CHOPPER_DEFAULT_12V`, stealthChop activo |
| Pasos/mm de fábrica | X 80, Y 80, Z 400, E 95 |
| Avance máximo de fábrica | X 2500, Y 2500, Z 100, E 25 mm/s |
| Avance máximo guardado por la suite | X 100, Y 100, Z 20, E 25 mm/s |
| Caja de software | X 4…319 mm, Y 2…306 mm, Z 0…400 mm |
| Inversión de DIR | X sí, Y sí, Z no, E0 sí, E1 no |
| Sensorless | Solo X, sensibilidad 100. Y, Z, E0 y E1 no lo tienen |
| Termistores | Ficticios, 25 °C. No hay sensor real |
| Extrusión en frío | Cortada de fábrica por debajo de 170 °C. La suite la abre con `M302 S0` |
| Largo máximo de un tramo E | 435 mm |
| Sensor de filamento | Compilado. La entrada lee TRIGGERED. La suite lo apaga con `M412 S0` |

`M569` en este Marlin elige stealthChop (`S1`) o spreadCycle (`S0`). No invierte el pin DIR. La dirección de una prueba se cambia con `sentido` en el archivo de configuración. Invertir el pin DIR de verdad es cambiar `INVERT_X_DIR` y sus equivalentes en `Configuration.h` y volver a grabar.

El fuente de Marlin no está en el repositorio. En la máquina de trabajo vive en `firmware/Marlin`, entorno PlatformIO `LPC1769`. El binario sale en `firmware/Marlin/.pio/build/LPC1769/firmware.bin`. Para grabarlo: tarjeta FAT32, archivo `firmware.bin` en la raíz, puente 5V SEL en +5V–VDD, fuente puesta, y reset. El cargador de la SKR copia el archivo y lo renombra a `FIRMWARE.CUR`. No hay botón BOOT. El USB no sirve para grabar este bootloader.

No mandar `M104`, `M109`, `M140` ni `M190`. Los termistores son ficticios y la protección térmica sigue compilada: un calentador encendido no tiene una medida real que lo corte.

## Entorno

Hace falta Python 3.11 o superior. Desde la carpeta del proyecto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`scripts/suite.py` también arranca sin esa instalación: agrega `src/` al camino de módulos. Los cinco `scripts/prueba_motor_*.py` solo usan pyserial y no pasan por el paquete.

Las pruebas del programa, sin abrir la placa:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Abrir COM3 reinicia el LPC1769, porque Windows afirma DTR. La suite espera un segundo antes de la primera orden.

## Cómo correr las pruebas

Con la fuente en 12 V, el puente en +5V–VDD, el USB conectado y los motores en vacío:

```powershell
.\.venv\Scripts\python.exe .\scripts\suite.py --listar
.\.venv\Scripts\python.exe .\scripts\suite.py --comandos
.\.venv\Scripts\python.exe .\scripts\suite.py --canal X
.\.venv\Scripts\python.exe .\scripts\suite.py
```

| Comando | Qué hace |
|---|---|
| `--listar` | Muestra cada canal: corriente, sentido, pasos, pines y vueltas de cada tramo. No abre el puerto |
| `--comandos` | Muestra el G-code que se enviaría. No abre el puerto |
| `--canal X` | Escribe las corrientes de todos los canales y mueve solo ese. Vale `X`, `Y`, `Z`, `E0` o `E1` |
| sin argumentos | Mueve los canales activos en el orden del archivo |

`--listar` se mira después de cada edición. Si una corriente pasa el techo, o un eje cartesiano se saldría de la caja, la suite se detiene antes de abrir el puerto y dice por qué.

Un canal con `activo = false` no se mueve. Su corriente igual se escribe, para que la placa quede como dice el archivo.

Los programas base siguen siendo ejecutables uno por uno. No los sustituye la suite:

```powershell
.\.venv\Scripts\python.exe .\scripts\prueba_motor_x.py
.\.venv\Scripts\python.exe .\scripts\prueba_motor_y.py
.\.venv\Scripts\python.exe .\scripts\prueba_motor_z.py
.\.venv\Scripts\python.exe .\scripts\prueba_motor_e0.py
.\.venv\Scripts\python.exe .\scripts\prueba_motor_e1.py
```

Esos cinco archivos tienen el puerto, la corriente y la secuencia escritos dentro. La copia de respaldo está en `BKP/` y no se ejecuta. La suite es la que centraliza las señales en `config/banco.toml`. Si se edita un número, se edita el TOML: los programas base no lo leen.

Otros comandos del paquete, sin mover motores:

```powershell
.\.venv\Scripts\python.exe -m tonf puertos
.\.venv\Scripts\python.exe -m tonf firmware
.\.venv\Scripts\python.exe -m tonf indicadores
```

`tonf enviar` espera un banner Grbl y no manda un archivo a este Marlin. Los motores se mueven con la suite o con el programa base del canal.

## Qué hace la suite, en orden

1. Lee `config/banco.toml` y rechaza el archivo si el techo, la caja, el home o el calentamiento no se pueden cumplir.
2. Abre el puerto. Eso reinicia la placa.
3. Ajuste, una sola vez: `M302`, `M412`, `M203`, `M906` de cada canal, `M569` de cada canal, `M92` y, si está pedido, `M500`.
4. Recorre los canales activos. En X, Y y Z: posición absoluta, `G92` al origen, modo relativo, los tramos y `M400` entre ellos. En E0 y E1: selecciona `T0` o `T1`, modo relativo de extrusor `M83`, `G92` y los mismos tramos.
5. Después de cada canal lee `M114`, `M122` y `M119`.
6. Cierra en absoluto, vuelve a `T0` y suelta los motores con `M18`.

Si la placa contesta `Error`, `Unknown command`, `cold extrusion` o `invalid extruder`, la suite se detiene, manda `M18` y no sigue con el canal siguiente.

No hay `G28`. Un home con el eje en vacío lo haría girar hasta ver un atasco. En Y, Z, E0 y E1 el sensorless ni siquiera está compilado. `seguridad.home` y `seguridad.calentar` tienen que quedarse en `false`. Ponerlos en `true` aborta la suite: no existe una rutina de home ni de calentamiento en este programa.

## El archivo config/banco.toml

Hay dos clases de campos. «En vivo» significa que la próxima corrida de la suite lo manda por el puerto. El resto queda escrito para no perder el dato del banco, y cambiarlo en el TOML no reprograma la placa.

| Campo | En vivo | Efecto |
|---|---|---|
| `enlace.puerto`, `baud`, `espera_apertura_s` | sí | Puerto, velocidad y pausa después del reset por DTR |
| `alimentacion.techo_ma` | no | Si alguna `corriente_ma` lo supera, la suite no arranca |
| `alimentacion.vmot_v`, `logica` | no | Registro. Hoy 12 V y puente +5V–VDD |
| `seguridad.home`, `seguridad.calentar` | no | Tienen que seguir en `false` |
| `maquina.extrusion_en_frio` | sí | `true` envía `M302 S0`. `false` vuelve a exigir 170 °C |
| `maquina.sensor_filamento` | sí | `false` envía `M412 S0`. Hay que dejarlo así |
| `maquina.origen_mm` | sí | `G92` antes de cada canal. Hoy 150 mm |
| `maquina.guardar_eeprom` | sí | `true` hace `M500` después del ajuste |
| `maquina.herramienta_al_final` | sí | `0` selecciona E0 al terminar. `-1` no manda `T` |
| `maquina.soltar_al_final` | sí | `true` manda `M18` |
| `maquina.extrusion_max_mm` | no | Un tramo de E más largo que esto se rechaza. Compilado en 435 mm |
| `avances_maximos_mm_s` | sí | `M203`. La unidad es mm/s |
| `limites_mm` | no | La suite no arranca si X, Y o Z fueran a salir de ese intervalo |
| `secuencia.*.movimientos` | sí | Los tramos `G1` y las esperas |
| `canales.*.corriente_ma` | sí | `M906`, en mA RMS |
| `canales.*.sentido` | sí | `1` o `-1`. Multiplica el signo de cada tramo |
| `canales.*.sigilo` | sí | `true` es stealthChop (`M569 S1`). `false` es spreadCycle (`M569 S0`) |
| `canales.*.pasos_por_mm` | sí | `M92`. E0 y E1 tienen que ser iguales |
| `canales.*.activo`, `orden`, `secuencia` | sí | Qué canales entran y en qué orden |
| `canales.*.origen_mm` | sí | Si está, reemplaza el origen general solo en ese canal |
| `canales.*.dir_invertido_compilado` | no | Copia de `INVERT_*_DIR`. No mueve el pin |
| `canales.*.micropasos`, `interpolar` | no | Compilados en 16 con interpolación. La suite no manda `M350` |
| `canales.*.rsense_*` | no | Registro. Ver la tabla de sensado |
| `canales.*.step`, `dir`, `enable`, `uart`, `diag` | no | Pines. No se cambian desde aquí |
| `maquina.retencion`, `chopper`, `plug` | no | Retención 0,5, chopper de 12 V y orden del plug |

E0 y E1 no pueden tener `pasos_por_mm` distintos. Este firmware no compila `DISTINCT_E_FACTORS`, así que `M92 E` escribe los dos a la vez. La suite lo rechaza.

`avance_mm_min` de cada tramo es la letra F de Marlin, en mm/min. `avances_maximos_mm_s` es `M203`, en mm/s. No son la misma unidad. 1800 mm/min son 30 mm/s.

### La secuencia en vacío

`[secuencia.vacio]` es el protocolo que ya corrió cada motor, ida y vuelta, sin home. `distancia_mm` es el tramo antes de aplicar `sentido`.

| Tramo | Avance F | En mm/s | Espera del `M400` |
|---|---|---|---|
| +10 mm y regreso | 300 mm/min | 5 | 20 s |
| +40 mm y regreso | 600 mm/min | 10 | 25 s |
| +40 mm y regreso | 1800 mm/min | 30 | 20 s |

`espera_comando_s` es el tiempo máximo para que la placa acepte la línea. `espera_fin_s` es el tiempo máximo de `M400`. En los tramos de 40 mm a 10 mm/s la placa suele imprimir `echo:busy: processing`: el eje se está moviendo, no está trabada.

El tramo rápido pide 30 mm/s. El tope guardado de Z es 20 mm/s y el de E es 25 mm/s, así que Marlin recorta ese avance en Z, E0 y E1. `--listar` lo avisa y la suite igual corre. X e Y tienen tope de 100 mm/s y ese tramo no se recorta.

Un tramo de distancia 0 se rechaza. En X, Y y Z la posición, partiendo de `origen_mm`, tiene que quedarse dentro de `limites_mm` después de cada tramo con su signo. En E, un solo tramo no puede pasar 435 mm.

Para darle a un canal otro recorrido se agrega una secuencia y se apunta desde el canal:

```toml
[canales.Z]
secuencia = "corta"

[[secuencia.corta.movimientos]]
distancia_mm = 2
avance_mm_min = 300
espera_comando_s = 5
espera_fin_s = 15

[[secuencia.corta.movimientos]]
distancia_mm = -2
avance_mm_min = 300
espera_comando_s = 5
espera_fin_s = 15
```

### Ediciones habituales

Bajar la corriente de Z a 600 mA:

```toml
[canales.Z]
corriente_ma = 600
```

Invertir el sentido de la prueba de Y, sin tocar cables ni el pin DIR:

```toml
[canales.Y]
sentido = -1
```

Sacar E1 de la pasada completa:

```toml
[canales.E1]
activo = false
```

Cambiar el orden, por ejemplo para que Z salga antes que Y: se editan los números `orden`. No pueden repetirse.

Pasar stealthChop a spreadCycle en un canal:

```toml
[canales.X]
sigilo = false
```

Eso manda `M569 X S0`. Volver a stealthChop es `sigilo = true`.

### Vueltas del eje

`--listar` las calcula así:

```text
vueltas = |distancia_mm| × pasos_por_mm / (360 / grados_por_paso × micropasos)
```

Con 1,8 ° y 16 micropasos hay 3200 pulsos por vuelta. Con los pasos de hoy:

| Canal | 10 mm | 40 mm |
|---|---|---|
| X y Y, 80 pasos/mm | 0,25 vueltas | 1,00 vuelta |
| Z, 400 pasos/mm | 1,25 vueltas | 5,00 vueltas |
| E0 y E1, 95 pasos/mm | 0,30 vueltas | 1,19 vueltas |

`grados_por_paso` solo entra en esa cuenta. Los pulsos los mandan `pasos_por_mm` y la distancia. Si un motor no es de 1,8 °, el número de vueltas de `--listar` no va a coincidir con el eje hasta corregir ese campo, y los pulsos seguirán siendo los de `pasos_por_mm`.

`M114` al final de un canal que fue y volvió tiene que mostrar otra vez el origen, 150 mm. El contador de pasos de X, Y y Z no cambia cuando el neto del movimiento es cero. Es lo esperado: `G92` cambia la posición lógica, no el contador.

## Cómo leer una corrida

Cada orden sale así:

```text
===== X: G1 X10 F300 =====
ok P14 B3
```

`ok` es una línea aceptada, también cuando viene como `ok P14 B3` o `ok P15 B3`. `P14` aparece mientras el planificador aún tiene movimiento. `P15` aparece con la cola vacía.

`M122` confirma el driver. Para dar el canal por comunicado tienen que verse:

- `Testing … connection... OK`
- la corriente pedida en `Set current`
- `stealthChop true`
- `msteps 16`
- sin `s2ga`, `s2gb` ni `ot`

`ola` es carga abierta en la bobina A. `olb` es carga abierta en la bobina B. `sg_result` es la lectura de StallGuard, no un encoder. `M114` es la posición que Marlin cree haber mandado, no una medida del eje. El TMC2209 de este banco no tiene encoder.

En la pasada conjunta del 5 de octubre de 2026 los cinco canales aceptaron los seis tramos y volvieron a 150 mm. Los cinco drivers contestaron. Quedó una marca de carga abierta en la bobina B de Y y en la bobina A de E1. X, Z y E0 no marcaron carga abierta, cortocircuito ni sobretemperatura. Si Y o E1 no giran parejos en los dos sentidos, se revisa el plug de ese zócalo y la continuidad de las dos bobinas antes de subir la corriente.

`M119` en reposo, con DIAG colocado y sin home, lee `x_min`, `y_min` y `z_min` en open. `filament: TRIGGERED` no frena el movimiento mientras `M412 S0` esté guardado.

Al cierre la suite deja `G90`, `T0` y `M18`: coordenadas absolutas, extrusor 0 seleccionado y motores sueltos.

## Qué no hace este programa

- No homea y no calibra un final de carrera.
- No enciende hotend, cama ni ventiladores por software.
- No sube una corriente por encima de `techo_ma`.
- No graba firmware ni cambia pines, micropasos, Rsense ni la inversión de DIR compilada.
- No mueve un sexto eje. ZBM no cuenta.
- `tonf enviar` no transmite G-code a este Marlin.

La precisión de un paso, con 80 pasos/mm y 16 micropasos, es 12,5 µm en la cuenta del comando. Eso no es la precisión del eje: no hay encoder, el home sensorless de X no se usa en estas pruebas, y `M114` no mide la posición real.
