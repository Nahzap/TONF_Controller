# TONF Controller

Banco de cinco motores sobre una BigTreeTech SKR V1.4 Turbo. El programa habla con la placa por USB, escribe las señales de cada canal y recorre los motores en vacío. No es un host de impresora 3D.

La placa medida corre Marlin 2.1.2, máquina «TONF SKR», compilado el 5 de octubre de 2026 a las 17:44:30. Los cinco zócalos llevan un TMC2209 en UART. Los canales se llaman X, Y, Z, E0 y E1. E0 es la herramienta T0 y E1 es la herramienta T1; los dos se mueven con la letra E.

El archivo que se edita para cambiar corrientes, avances, sentidos, umbral StallGuard y recorridos es `config/banco.toml`. La pasada de los cinco canales es `scripts/suite.py`. Cada canal también tiene su programa en `scripts/`, y `BKP/` guarda la copia vigente de esos cinco programas.

Repositorio: https://github.com/Nahzap/TONF_Controller.git

Este README es el documento de operación. Las notas con fecha y hora viven en `Docs/` y no forman parte del repositorio. La nota de este estado es `Docs/2026-10-05_1825_avances-suite-terminal.md`.

El 5 de octubre de 2026, a las 18:25, la suite ya informaba por la terminal mientras corría y los cinco motores se movían.

## Qué hay que tener conectado

| Pieza | Dato de este banco |
|---|---|
| Placa | BTT SKR V1.4 Turbo, MCU NXP LPC1769 a 120 MHz |
| Drivers | Cinco TMC2209 BTT, uno por zócalo, UART de un hilo, dirección 0 |
| Fuente de motores | 12 V en el bornero DCIN. La placa admite 12–24 V |
| Lógica | Puente 5V SEL entre +5V y VDD. El USB solo lleva datos |
| Enlace | USB-B, puerto COM3, 115200 baudios, salto de línea |
| Motores | X, Y, Z, E0 y E1 |

ZBM, el segundo bornero de Z, va en paralelo con el driver Z. No es un sexto eje. El header de seis pines que hay junto a cada eje (STEP, DIR, EN, 3,3 V, GND, VBB) es para un driver externo de lazo cerrado.

No se inserta ni se retira un módulo TMC2209 con la fuente puesta. La orientación del módulo sigue el serigrafiado: EN y VMOT hacia los bornes del motor, DIR y GND hacia el MCU. Un módulo al revés quema el driver.

El orden del plug del motor, del lado del zócalo, es `1B 1A 2A 2B`.

### Puente 5V SEL

El jumper J15 tiene tres pines, de izquierda a derecha: USB, +5V, VDD.

- USB unido a +5V: la lógica sale del PC. Sirve para hablar con el MCU. VMOT sigue apagado y los drivers no contestan por UART.
- +5V unido a VDD: la lógica sale de la fuente de 12 V. Es la posición para mover motores. El USB queda solo en datos.
- USB puesto, puente en +5V–VDD y fuente apagada: el MCU no arranca.

FAN1, FAN2 y FAN3 quedan a la tensión de la fuente en cuanto hay 12 V. El firmware no los apaga.

### Jumpers de cada TMC2209

Un solo puente por zócalo, en el par UART / MS3 (el recuadro que queda junto a los bornes del motor). MS1, MS2 y los cuatro puentes SPI van sin jumper. MS1 o MS2 cambian la dirección UART y el módulo deja de contestar en la dirección 0.

En los módulos BTT el pin PDN ya está unido al header. DIAG del módulo entra en el zócalo y es el mismo pin que el final de carrera de ese eje. Un final mecánico exigiría sacar DIAG. Esta suite no usa finales mecánicos ni hace home.

ENABLE es activo en bajo. Un nivel alto en ENN apaga el puente del driver.

Abrir COM3 reinicia el LPC1769, porque Windows afirma DTR. La suite espera un segundo antes de la primera orden. VMOT tiene que estar presente para que el UART del TMC2209 conteste.

## Árbol

```text
README.md                  este documento
pyproject.toml             paquete Python tonf-controller 0.1.0
config/banco.toml          señales de los cinco canales
scripts/suite.py           prueba unificada, orden X Y Z E0 E1
scripts/prueba_motor_*.py  prueba de un canal. Son los programas base
BKP/                       copia vigente de esos cinco programas
src/tonf/                  enlace, medidas y la suite
tests/                     pruebas del programa, sin abrir la placa
Docs/                      notas locales con fecha y hora
firmware/Marlin            fuente local de Marlin 2.1.2, fuera del repositorio
```

No entran al repositorio `Docs/`, `.venv/`, la caché de pytest, `reports/` ni `firmware/`.

## Motores y corrientes

`corriente_ma` es la corriente RMS que Marlin escribe con `M906`. El techo del banco es 800 mA. La suite no arranca si algún canal lo pasa.

| Canal | Cómo se mueve | Motor | Corriente | Nominal de catálogo | Pasos/mm | DIR compilado |
|---|---|---|---|---|---|---|
| X | `G1 X`, `M906 X`, `M914 X` | Sin nombre de catálogo | 450 mA | — | 80 | invertido |
| Y | `G1 Y`, `M906 Y`, `M914 Y` | CF3925-100-SL | 800 mA | no hay ficha | 80 | invertido |
| Z | `G1 Z`, `M906 Z`, `M914 Z` | SY42STH38-1684A | 800 mA | 1680 mA por fase | 400 | directo |
| E0 | `T0`, letra E, `M906 T0 E`, `M914 T0 E` | SY42STH38-1684A | 800 mA | 1680 mA por fase | 95 | invertido |
| E1 | `T1`, letra E, `M906 T1 E`, `M914 T1 E` | CF3925-100-SL | 800 mA | no hay ficha | 95 | directo |

X se dejó en 450 mA porque en el banco ese motor se movió entre 400 y 500 mA. Y, Z, E0 y E1 están en el tope de 800 mA. Z y E0 se nombraron en el banco como SY52STH38 1684A; el catálogo de 1,68 A por fase es el SY42STH38-1684A. Del CF3925-100-SL no hay corriente de fabricante en este banco. El cálculo de vueltas de ese modelo supone 1,8 ° por paso.

`M906 E800` sin índice escribe E0 y E1 a la vez. La suite manda `M906 T0 E800` y `M906 T1 E800`. E0 y E1 tienen que compartir `pasos_por_mm`: este firmware no compila `DISTINCT_E_FACTORS`, así que `M92 E` escribe los dos. Hoy los dos están en 95.

### Resistencia de sensado

El módulo BTT mide 0,11 Ω. El firmware compilado no usa ese valor en todos los canales, y la suite no puede cambiarlo por el puerto. Mientras no coincidan, el número de `M906` no es la corriente real de la bobina. La suite lo avisa en cada corrida.

| Canal | Rsense compilada | Rsense del módulo | Con la consigna de la suite, M906 reportó |
|---|---|---|---|
| X | 0,0 Ω | 0,11 Ω | 397 mA al pedir 450 mA |
| Y | 0,062 Ω | 0,11 Ω | 776 mA al pedir 800 mA |
| Z | 0,062 Ω | 0,11 Ω | 776 mA al pedir 800 mA |
| E0 | 0,062 Ω | 0,11 Ω | 776 mA al pedir 800 mA |
| E1 | 0,11 Ω | 0,11 Ω | 795 mA al pedir 800 mA |

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

Con sensorless de X e Y, el mapa de la SKR también presenta E0DET como fin máximo de X y E1DET como fin máximo de Y, y los mismos pines como sensor de filamento. Por eso la suite manda `M412 S0`. `M119` puede mostrar `filament: TRIGGERED` sin frenar E0 ni E1.

## Firmware que corre la placa

Marlin 2.1.2, `MACHINE_TYPE` «TONF SKR», `EXTRUDER_COUNT` 2, USB en `SERIAL_PORT -1` a 115200. Identidad con `M115`. La cadena de compilación leída en la placa es `Oct  5 2026 17:44:30`. El binario de esa grabación mide 206024 bytes.

| Parámetro compilado | Valor |
|---|---|
| Drivers | TMC2209 en X, Y, Z, E0 y E1 |
| Micropasos | 16, con interpolación a 256 |
| Chopper | `CHOPPER_DEFAULT_12V`, stealthChop activo |
| Pasos/mm de fábrica | X 80, Y 80, Z 400, E 95 |
| Avance máximo de fábrica | X 2500, Y 2500, Z 100, E 25 mm/s |
| Avance máximo que guarda la suite | X 100, Y 100, Z 20, E 25 mm/s |
| Caja de software | X 4…319 mm, Y 2…306 mm, Z 0…400 mm |
| Inversión de DIR | X sí, Y sí, Z no, E0 sí, E1 no |
| StallGuard | Umbral 100 en los cinco. `M914 X`, `M914 Y`, `M914 Z`, `M914 T0 E`, `M914 T1 E` |
| Home sensorless | X, Y y Z pueden usar `G28`. E0 y E1 tienen el umbral en el driver; `G28` no homea un extrusor |
| Termistores | Ficticios, 25 °C. Sensores 0 y cama en modo 998 |
| Extrusión en frío | La suite la abre con `M302 S0` |
| Sensor de filamento | Compilado. La suite lo apaga con `M412 S0` |
| Retención | `HOLD_MULTIPLIER` 0,5 |

`M569` en este Marlin elige stealthChop (`S1`) o spreadCycle (`S0`). No invierte el pin DIR. La dirección de una prueba se cambia con `sentido` en el archivo de configuración. Invertir el pin DIR de verdad es cambiar `INVERT_*_DIR` en `Configuration.h` y volver a grabar.

`M914` sin argumentos responde las cinco sensibilidades: X, Y, Z, E y E1. En TMC2209 el valor va de 0 a 255. Un número más alto dispara con menos carga.

Después de grabar el firmware del 17:44, la EEPROM vieja dejó el umbral de Y y de Z en 0. E0 y E1 salieron en 100 porque el fuente nuevo los escribe al iniciar y no ocupan los huecos viejos de X Y Z. La suite manda los cinco umbrales y, con `guardar_eeprom = true`, los fija con `M500`.

No mandar `M104`, `M109`, `M140` ni `M190`. Los termistores son ficticios.

### Grabar otro firmware.bin

El fuente no está en el repositorio. En la máquina de trabajo vive en `firmware/Marlin`, entorno PlatformIO `LPC1769`. Desde esa carpeta, el PlatformIO del proyecto es:

```powershell
D:\TONF_Controller\.venv\Scripts\pio.exe run -e LPC1769
```

El binario sale en `firmware/Marlin/.pio/build/LPC1769/firmware.bin`.

La grabación que funcionó en esta placa:

1. Puente 5V SEL en +5V–VDD y fuente de 12 V puesta.
2. USB conectado. La tarjeta aparece como volumen FAT32 de Marlin (en esta máquina, `E:`).
3. Copiar `firmware.bin` a la raíz de ese volumen.
4. Desmontar el volumen.
5. Enviar `M997` por COM3. El cargador renombra el archivo a `FIRMWARE.CUR` y arranca el binario nuevo.
6. Abrir el puerto otra vez y leer `M115`. La fecha de compilación tiene que coincidir con el binario recién copiado.

No hay botón BOOT. El pin que en otras SKR entra a DFU está usado como ENABLE de E0, y el DFU por USB está fuera de este bootloader. Copiar el archivo a una letra de unidad que no sea el volumen de la SKR no graba la placa.

## Entorno

Hace falta Python 3.11 o superior. Desde la carpeta del proyecto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`scripts/suite.py` también arranca sin esa instalación: agrega `src/` al camino de módulos. Los cinco `scripts/prueba_motor_*.py` usan pyserial y no leen `config/banco.toml`.

Las pruebas del programa, sin abrir la placa, son 24:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Cómo correr las pruebas

Con la fuente en 12 V, el puente en +5V–VDD, el USB conectado y los motores en vacío:

```powershell
.\.venv\Scripts\python.exe .\scripts\suite.py --listar
.\.venv\Scripts\python.exe .\scripts\suite.py --comandos
.\.venv\Scripts\python.exe .\scripts\suite.py --canal E0
.\.venv\Scripts\python.exe .\scripts\suite.py
```

| Comando | Qué hace |
|---|---|
| `--listar` | Muestra cada canal: corriente, sentido, StallGuard, pasos, pines y vueltas de cada tramo. No abre el puerto |
| `--comandos` | Muestra el G-code que se enviaría. No abre el puerto |
| `--canal E0` | Escribe las corrientes de todos los canales y mueve solo ese. Vale `X`, `Y`, `Z`, `E0` o `E1` |
| sin argumentos | Mueve los canales activos en el orden del archivo |

`--listar` se mira después de cada edición. Si una corriente pasa el techo, si E0 y E1 tienen pasos distintos, o si X, Y o Z se saldrían de la caja, la suite se detiene antes de abrir el puerto y dice por qué.

Un canal con `activo = false` no se mueve. Su corriente igual se escribe, para que la placa quede como dice el archivo.

La terminal es la evidencia de la corrida. Al abrir la suite aparecen el puerto, los avisos de Rsense o de avance recortado, y la línea de que el puerto reinicia la placa. Después, cada grupo y cada orden se imprimen antes de mandarlos, y la respuesta entra en la misma ventana en cuanto la placa la envía. Durante un `M400` largo se ven líneas `echo:busy: processing`: el eje se está moviendo.

Los programas base siguen siendo ejecutables uno por uno. La suite no los reemplaza:

```powershell
.\.venv\Scripts\python.exe .\scripts\prueba_motor_x.py
.\.venv\Scripts\python.exe .\scripts\prueba_motor_y.py
.\.venv\Scripts\python.exe .\scripts\prueba_motor_z.py
.\.venv\Scripts\python.exe .\scripts\prueba_motor_e0.py
.\.venv\Scripts\python.exe .\scripts\prueba_motor_e1.py
```

Cada uno anuncia el canal, abre COM3 y va imprimiendo la orden y la respuesta. E0 selecciona `T0` y mueve con E. E1 selecciona `T1`, mueve con E y al final vuelve a `T0`. Esos archivos tienen el puerto, la corriente y la secuencia escritos dentro. `BKP/` es la copia de esos cinco archivos tal como quedaron cuando los tests del programa pasaron. `BKP/` no se ejecuta. Si se edita un número de la pasada conjunta, se edita el TOML.

Otros comandos del paquete, sin mover motores:

```powershell
.\.venv\Scripts\python.exe -m tonf puertos
.\.venv\Scripts\python.exe -m tonf firmware
.\.venv\Scripts\python.exe -m tonf indicadores
```

`tonf enviar` espera un banner Grbl y no manda un archivo a este Marlin. Los motores se mueven con la suite o con el programa base del canal.

## Qué hace la suite, en orden

1. Lee `config/banco.toml` y rechaza el archivo si el techo, la caja, los pasos de E0 y E1, el home o el calentamiento no se pueden cumplir.
2. Escribe en la terminal el puerto y los avisos. Abre COM3. Eso reinicia la placa.
3. Ajuste, una sola vez, bajo el grupo `ajuste`: `M302 S0`, `M412 S0`, `M203 X100 Y100 Z20 E25`, `M906` de cada canal, `M569` de cada canal, `M914` de cada canal, `M92 X80 Y80 Z400 E95` y, si está pedido, `M500`. Luego relee `M906`, `M92`, `M569` y `M914`.
4. Recorre los canales activos. En X, Y y Z el grupo se llama como el canal: `G90`, `G92` al origen, `G91`, los tramos y `M400` entre ellos. En E0 el grupo se llama `E0`: `T0`, `M83`, `G92 E150` y `G1 E`. En E1 el grupo se llama `E1`: `T1`, `M83`, `G92 E150` y `G1 E`.
5. Después de cada canal lee `M114`, `M122`, `M914` y `M119`.
6. Cierra en absoluto, selecciona `T0` (E0) y suelta los motores con `M18`.

Si la placa contesta `Error`, `Unknown command`, `cold extrusion` o `invalid extruder`, la suite imprime `DETENIDO`, manda `M18` y no sigue con el canal siguiente.

No hay `G28` en la suite. Un home con el eje en vacío lo haría girar hasta ver un atasco. X, Y y Z pueden homear por StallGuard. E0 y E1 tienen el mismo umbral cargado en el TMC2209; Marlin no homea un extrusor, y el nombre de esos canales sigue siendo E0 y E1. `seguridad.home` y `seguridad.calentar` tienen que quedarse en `false`. Ponerlos en `true` aborta la suite: no existe una rutina de home ni de calentamiento en este programa.

## El archivo config/banco.toml

Hay dos clases de campos. «En vivo» significa que la próxima corrida de la suite lo manda por el puerto. El resto queda escrito para quien hereda el banco, y cambiarlo en el TOML no reprograma la placa.

| Campo | En vivo | Efecto |
|---|---|---|
| `enlace.puerto`, `baud`, `espera_apertura_s` | sí | Puerto, velocidad y pausa después del reset por DTR. Hoy COM3, 115200, 1 s |
| `alimentacion.techo_ma` | no | Si alguna `corriente_ma` lo supera, la suite no arranca. Hoy 800 |
| `alimentacion.vmot_v`, `logica` | no | Registro. Hoy 12 V y puente +5V–VDD |
| `seguridad.home`, `seguridad.calentar` | no | Tienen que seguir en `false` |
| `maquina.origen_mm` | sí | `G92` antes de cada canal. Hoy 150 mm |
| `maquina.extrusion_en_frio` | sí | `true` envía `M302 S0` para poder mover E0 y E1 |
| `maquina.extrusion_min_c` | sí | Solo si `extrusion_en_frio` es `false`. Compilado en 170 °C |
| `maquina.sensor_filamento` | sí | `false` envía `M412 S0` |
| `maquina.guardar_eeprom` | sí | `true` hace `M500` después del ajuste |
| `maquina.herramienta_al_final` | sí | `0` selecciona E0 al terminar. `-1` no manda `T` |
| `maquina.soltar_al_final` | sí | `true` manda `M18` |
| `maquina.extrusion_max_mm` | no | Un tramo de E0 o E1 más largo que esto se rechaza. Compilado en 435 mm |
| `avances_maximos_mm_s` | sí | `M203` de X, Y, Z y E. La unidad es mm/s. Hoy 100, 100, 20 y 25 |
| `limites_mm` | no | La suite no arranca si X, Y o Z fueran a salir de ese intervalo |
| `secuencia.*.movimientos` | sí | Los tramos `G1` y las esperas |
| `canales.*.corriente_ma` | sí | `M906`, en mA RMS |
| `canales.*.sentido` | sí | `1` o `-1`. Multiplica el signo de cada tramo |
| `canales.*.sigilo` | sí | `true` es stealthChop (`M569 S1`). `false` es spreadCycle (`M569 S0`) |
| `canales.*.pasos_por_mm` | sí | `M92`. E0 y E1 tienen que ser iguales |
| `canales.*.sensibilidad_stall` | sí | `M914`, de 0 a 255. Hoy 100 en los cinco |
| `canales.*.letra` | sí | X, Y, Z o E. E0 y E1 usan E |
| `canales.*.herramienta` | sí | Solo E0 (`0`) y E1 (`1`) |
| `canales.*.activo`, `orden`, `secuencia` | sí | Qué canales entran y en qué orden |
| `canales.*.origen_mm` | sí | Si está, reemplaza el origen general solo en ese canal |
| `canales.*.dir_invertido_compilado` | no | Copia de `INVERT_*_DIR`. No mueve el pin |
| `canales.*.micropasos`, `interpolar` | no | Compilados en 16 con interpolación. La suite no manda `M350` |
| `canales.*.rsense_*` | no | Registro. Ver la tabla de sensado |
| `canales.*.step`, `dir`, `enable`, `uart`, `diag` | no | Pines. No se cambian desde aquí |
| `maquina.retencion`, `chopper`, `plug`, `enable_activo_bajo` | no | Retención 0,5, chopper de 12 V, orden del plug y ENABLE activo en bajo |

`avance_mm_min` de cada tramo es la letra F de Marlin, en mm/min. `avances_maximos_mm_s` es `M203`, en mm/s. 1800 mm/min son 30 mm/s.

### La secuencia en vacío

`[secuencia.vacio]` es el protocolo de cada motor, ida y vuelta, sin home. `distancia_mm` es el tramo antes de aplicar `sentido`.

| Tramo | Avance F | En mm/s | Espera del comando | Espera del `M400` |
|---|---|---|---|---|
| +10 mm | 300 mm/min | 5 | 5 s | 20 s |
| −10 mm | 300 mm/min | 5 | 5 s | 20 s |
| +40 mm | 600 mm/min | 10 | 5 s | 25 s |
| −40 mm | 600 mm/min | 10 | 5 s | 25 s |
| +40 mm | 1800 mm/min | 30 | 5 s | 20 s |
| −40 mm | 1800 mm/min | 30 | 5 s | 20 s |

`espera_comando_s` es el tiempo máximo para que la placa acepte la línea. `espera_fin_s` es el tiempo máximo de `M400`.

El tramo rápido pide 30 mm/s. El tope guardado de Z es 20 mm/s y el de E es 25 mm/s, así que Marlin recorta ese avance en Z, E0 y E1. `--listar` lo avisa y la suite igual corre. X e Y tienen tope de 100 mm/s y ese tramo no se recorta.

Un tramo de distancia 0 se rechaza. En X, Y y Z la posición, partiendo de `origen_mm`, tiene que quedarse dentro de `limites_mm` después de cada tramo con su signo. En E0 y E1 un tramo no puede pasar 435 mm.

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

Subir el umbral StallGuard de E0:

```toml
[canales.E0]
sensibilidad_stall = 140
```

Eso manda `M914 T0 E140`. El canal sigue llamándose E0.

Cambiar el orden, por ejemplo para que Z salga antes que Y: se editan los números `orden`. No pueden repetirse.

Pasar stealthChop a spreadCycle en un canal:

```toml
[canales.X]
sigilo = false
```

Eso manda `M569 X S0`. En E1 el mismo campo manda `M569 T1 E S0`. Volver a stealthChop es `sigilo = true`.

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

`M114` al final de un canal que fue y volvió tiene que mostrar otra vez el origen, 150 mm. En E0 y E1 esa posición es la E lógica. El contador de pasos de X, Y y Z no cambia cuando el neto del movimiento es cero. Es lo esperado: `G92` cambia la posición lógica, no el contador. Que `M400` haya estado ocupado indica que el tramo se ejecutó.

## Cómo leer una corrida

El arranque y un tramo de X se ven así. La respuesta aparece debajo de la orden, en el momento en que llega:

```text
Suite en COM3 a 115200 baudios.
Aviso: X: el firmware tiene Rsense 0 Ω y el módulo es 0.11 Ω. ...
Abriendo COM3. El puerto reinicia la placa.

----- X -----
===== G1 X10 F300 =====
ok P15 B3
===== M400 =====
echo:busy: processing
ok P14 B3
```

En E0 el grupo se llama E0 y el movimiento usa T0 y la letra E:

```text
----- E0 -----
===== T0 =====
ok
===== M83 =====
ok
===== G92 E150 =====
ok
===== G1 E10 F300 =====
ok
===== M400 =====
echo:busy: processing
ok
```

E1 es el mismo esquema con el grupo `E1`, `T1` y `G1 E`.

`ok` es una línea aceptada, también cuando viene como `ok P14 B3` o `ok P15 B3`. `P14` aparece mientras el planificador aún tiene movimiento. `P15` aparece con la cola vacía.

`M122` confirma el driver. Para dar el canal por comunicado tienen que verse:

- `Testing … connection... OK` en X, Y, Z, E y E1
- la corriente pedida en `Set current`
- `stealthChop true`
- `msteps 16`
- `Stallguard thrs` en 100 en las cinco columnas
- sin `s2ga`, `s2gb` ni `ot`

`M914` sin argumentos tiene que listar:

```text
X homing sensitivity: 100
Y homing sensitivity: 100
Z homing sensitivity: 100
E homing sensitivity: 100
E1 homing sensitivity: 100
```

`ola` es carga abierta en la bobina A. `olb` es carga abierta en la bobina B. `sg_result` es la lectura de StallGuard, no un encoder. `M114` es la posición que Marlin cree haber mandado, no una medida del eje. El TMC2209 de este banco no tiene encoder.

En la pasada conjunta del 5 de octubre de 2026 los cinco canales aceptaron los seis tramos y volvieron a 150 mm. Los cinco drivers contestaron y el umbral StallGuard quedó en 100. Quedó una marca de carga abierta en la bobina B de Y y en la bobina A de E1. X, Z y E0 no marcaron carga abierta, cortocircuito ni sobretemperatura. Si Y o E1 no giran parejos en los dos sentidos, se revisa el plug de ese zócalo y la continuidad de las dos bobinas antes de subir la corriente. A las 18:25 de ese día la corrida ya mostraba la evidencia en la terminal y los cinco motores se movían, con E0 y E1 por su nombre.

`M119` en reposo, con DIAG colocado y sin home, lee `x_min`, `y_min` y `z_min` en open. `filament` puede leer TRIGGERED; con `M412 S0` eso no frena E0 ni E1.

Al cierre la suite deja `G90`, `T0` y `M18`: coordenadas absolutas, E0 seleccionado y motores sueltos.

## Qué no hace este programa

- No homea y no calibra un final de carrera. No manda `G28`.
- No enciende hotend, cama ni ventiladores por software.
- No sube una corriente por encima de `techo_ma`.
- No graba firmware ni cambia pines, micropasos, Rsense ni la inversión de DIR compilada.
- No renombra E0 ni E1. Esos zócalos se siguen llamando así.
- No mueve un sexto eje. ZBM no cuenta.
- `tonf enviar` no transmite G-code a este Marlin.

La precisión de un paso, con 80 pasos/mm y 16 micropasos, es 12,5 µm en la cuenta del comando. Eso no es la precisión del eje: no hay encoder, el home sensorless no se usa en estas pruebas, y `M114` no mide la posición real.
