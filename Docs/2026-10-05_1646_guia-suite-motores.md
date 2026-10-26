# Guía de la suite de motores

Fecha: 5 de octubre de 2026, 16:46.

Esta guía es para quien va a mover los cinco motores. El archivo que se edita es `config/banco.toml`. La suite lee ese archivo, escribe las señales en la placa y después recorre los canales activos, uno detrás de otro.

La placa es una BTT SKR V1.4 Turbo con Marlin 2.1.2, máquina «TONF SKR», y cinco módulos TMC2209 en UART. El mapa de pines y la alimentación están detallados en `Docs/2026-10-05_1152_SKR-v1.4-Turbo-TMC2209.md`.

## 1. Antes de mover nada

1. Fuente de motores en 12 V. El puente 5V SEL queda entre +5V y VDD, así la lógica sale de la fuente y el USB solo lleva datos.
2. USB en COM3, 115200 baudios. Abrir el puerto reinicia la placa: es normal que el enlace tarde cerca de un segundo.
3. Los motores de esta suite se prueban en vacío, sin una carrera mecánica que los detenga.
4. La suite no hace home y no enciende calentadores. Los termistores están en modo ficticio, a 25 °C. No mandar `M104`, `M109`, `M140` ni `M190`.

El orden del conector de cada motor, del lado del zócalo, es `1B 1A 2A 2B`.

## 2. Tres formas de usar la suite

Desde `D:\TONF_Controller`:

```powershell
.\.venv\Scripts\python.exe .\scripts\suite.py --listar
.\.venv\Scripts\python.exe .\scripts\suite.py --comandos
.\.venv\Scripts\python.exe .\scripts\suite.py
```

| Comando | Qué hace |
|---|---|
| `--listar` | Muestra cada canal: corriente, sentido, pasos, pines y vueltas de cada tramo. No abre el puerto. |
| `--comandos` | Muestra el G-code que se enviaría. No abre el puerto. |
| `--canal X` | Escribe las corrientes de todos los canales y mueve solo ese. Vale `X`, `Y`, `Z`, `E0` o `E1`. |
| sin argumentos | Mueve los canales activos en el orden del archivo: X, Y, Z, E0, E1. |

Conviene mirar `--listar` después de cada edición. Si un número deja el eje fuera de la caja, o una corriente pasa el techo, la suite se detiene antes de abrir el puerto y explica el motivo.

Un canal con `activo = false` no se mueve. Su corriente igual se escribe, para que la placa quede como dice el archivo.

## 3. Qué se edita en vivo y qué queda solo escrito

La columna «en vivo» es lo que la próxima corrida de la suite manda por el puerto. El resto está en el archivo para no perderlo, y cambiarlo ahí no reprograma la placa.

| Campo | En vivo | Efecto |
|---|---|---|
| `enlace.puerto`, `baud` | sí | Puerto serie |
| `alimentacion.techo_ma` | no | Si alguna `corriente_ma` lo supera, la suite no arranca. No hay un comando de techo |
| `alimentacion.vmot_v`, `logica` | no | Registro de la fuente. Hoy 12 V y puente +5V–VDD |
| `seguridad.home`, `seguridad.calentar` | no | Tienen que seguir en `false`. `true` aborta: esta suite no manda `G28` ni enciende calentadores |
| `maquina.extrusion_en_frio` | sí | `true` envía `M302 S0` y permite mover E en frío. `false` vuelve a exigir 170 °C |
| `maquina.sensor_filamento` | sí | `false` envía `M412 S0`. Hay que dejarlo así: la entrada de filamento lee TRIGGERED |
| `maquina.origen_mm` | sí | `G92` antes de cada canal. Hoy 150 mm, dentro de la caja |
| `maquina.guardar_eeprom` | sí | `true` hace `M500` después del ajuste |
| `maquina.herramienta_al_final` | sí | `0` deja seleccionado E0 al terminar. `-1` no manda `T` |
| `maquina.soltar_al_final` | sí | `true` manda `M18` y suelta los motores |
| `avances_maximos_mm_s` | sí | `M203`. La unidad es mm/s |
| `limites_mm` | no | La suite no arranca si un eje X, Y o Z fuera a salir de ese intervalo |
| `secuencia.*.movimientos` | sí | Los tramos `G1` y las esperas |
| `canales.*.corriente_ma` | sí | `M906`, en mA RMS |
| `canales.*.sentido` | sí | `1` o `-1`. Multiplica el signo de cada tramo |
| `canales.*.sigilo` | sí | `true` es stealthChop (`M569 S1`). `false` es spreadCycle (`M569 S0`) |
| `canales.*.pasos_por_mm` | sí | `M92`. E0 y E1 tienen que ser iguales: el firmware no trae `DISTINCT_E_FACTORS` |
| `canales.*.activo`, `orden`, `secuencia` | sí | Qué canales entran y en qué orden |
| `canales.*.dir_invertido_compilado` | no | Copia de `INVERT_*_DIR`. Para cambiar el pin DIR hay que editar `firmware/Marlin/Marlin/Configuration.h` y grabar de nuevo, o usar `sentido` |
| `canales.*.micropasos`, `interpolar` | no | Compilados en 16 micropasos con interpolación a 256. La suite no manda `M350` |
| `canales.*.rsense_*` | no | El módulo BTT es 0,11 Ω. El fuente de X, Y, Z y E0 no usa ese valor. Ver la sección 6 |
| `canales.*.step`, `dir`, `enable`, `uart`, `diag` | no | Pines del LPC1769. No se cambian desde el archivo |
| `maquina.retencion`, `chopper`, `plug` | no | Retención 0,5, chopper de 12 V y orden del plug |

`M569` en este Marlin elige stealthChop o spreadCycle. No invierte la dirección. La dirección de la prueba se cambia con `sentido`.

## 4. La secuencia

`[secuencia.vacio]` es el protocolo que ya corrió cada motor, en vacío:

| Tramo | Avance F | En mm/s |
|---|---|---|
| +10 mm y regreso | 300 mm/min | 5 |
| +40 mm y regreso | 600 mm/min | 10 |
| +40 mm y regreso | 1800 mm/min | 30 |

`distancia_mm` es el tramo antes de aplicar `sentido`. `avance_mm_min` es la letra F de Marlin, en mm/min. No mezclarla con `M203`, que va en mm/s.

`espera_comando_s` es cuánto puede tardar la placa en aceptar la línea. `espera_fin_s` es la espera de `M400`, que no vuelve hasta que el movimiento terminó. En los tramos largos la placa puede imprimir `echo:busy: processing`: el eje se está moviendo.

Para darle a un solo canal una secuencia distinta, se agrega otra y se apunta desde el canal:

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

Un tramo de distancia 0 se rechaza. En X, Y y Z la suma de los tramos, desde `origen_mm`, tiene que quedarse dentro de `limites_mm`. Hoy esa caja es X 4…319 mm, Y 2…306 mm y Z 0…400 mm. En E, un solo tramo no puede pasar `extrusion_max_mm` (435 mm).

## 5. Ediciones habituales

Bajar la corriente de Z a 600 mA, sin pasar el techo de 800:

```toml
[canales.Z]
corriente_ma = 600
```

Invertir el sentido en el que Y hace la prueba, sin tocar el cableado:

```toml
[canales.Y]
sentido = -1
```

Sacar E1 de la pasada completa y dejarlo para más adelante:

```toml
[canales.E1]
activo = false
```

Correr después solo ese canal, cuando vuelva a estar activo:

```powershell
.\.venv\Scripts\python.exe .\scripts\suite.py --canal E1
```

Cambiar el orden para que Z salga antes que Y: se editan los números `orden`. No pueden repetirse.

El avance máximo de E, en mm/s:

```toml
[avances_maximos_mm_s]
E = 25
```

El tramo rápido de la secuencia pide 30 mm/s en E. Con el tope en 25 mm/s, Marlin recorta ese avance. `--listar` lo avisa y la suite igual corre.

## 6. Corriente y resistencia de sensado

`corriente_ma` es el valor RMS que Marlin escribe con `M906`. El techo del banco es 800 mA. X queda en 450 mA porque ese motor se movió entre 400 y 500 mA. Y, Z, E0 y E1 quedan en 800 mA.

| Canal | Motor | Corriente de la suite | Nominal |
|---|---|---|---|
| X | Sin nombre de catálogo | 450 mA | — |
| Y | CF3925-100-SL | 800 mA | No hay valor de catálogo |
| Z | SY42STH38-1684A | 800 mA | 1680 mA por fase |
| E0 | SY42STH38-1684A | 800 mA | 1680 mA por fase |
| E1 | CF3925-100-SL | 800 mA | No hay valor de catálogo |

Z y E0 se nombraron en el banco como SY52STH38 1684A. El catálogo de 1,68 A por fase es el SY42STH38-1684A.

E0 y E1 no se ajustan con `M906 E`. En este Marlin eso escribe los dos extrusores. La suite manda `M906 T0 E800` y `M906 T1 E800`.

El módulo BTT tiene una resistencia de sensado de 0,11 Ω. El firmware compilado no usa ese número en todos los canales:

| Canal | Rsense en el fuente | Rsense del módulo |
|---|---|---|
| X | 0,0 Ω | 0,11 Ω |
| Y | 0,062 Ω | 0,11 Ω |
| Z | 0,062 Ω | 0,11 Ω |
| E0 | 0,062 Ω | 0,11 Ω |
| E1 | 0,11 Ω | 0,11 Ω |

Mientras esos dos números no coincidan, el mA que muestra `M906` no es la corriente real de la bobina. Corregirlo es editar `*_RSENSE` en `firmware/Marlin/Marlin/Configuration_adv.h` y grabar otro `firmware.bin`. La suite no puede hacerlo por el puerto, y por eso lo avisa en cada corrida. E1 es el único canal en el que los dos valores ya coinciden: ahí 800 mA de consigna se reportó como 795 mA RMS.

La corriente de reposo es la mitad de la de marcha (`retencion = 0.5`), salvo el redondeo del driver. En X, con 450 mA, esa mitad cae a un escalón que el driver muestra como 0.

## 7. Vueltas del eje

`--listar` calcula las vueltas así:

```text
vueltas = |distancia_mm| × pasos_por_mm / (360 / grados_por_paso × micropasos)
```

Con 1,8 ° y 16 micropasos hay 3200 pulsos por vuelta. Con los pasos/mm de hoy:

| Canal | 10 mm | 40 mm |
|---|---|---|
| X y Y, 80 pasos/mm | 0,25 vueltas | 1,00 vuelta |
| Z, 400 pasos/mm | 1,25 vueltas | 5,00 vueltas |
| E0 y E1, 95 pasos/mm | 0,30 vueltas | 1,19 vueltas |

En el CF3925-100-SL ese cálculo supone 1,8 °. No hay una ficha del fabricante en el banco que lo confirme. Si un motor es de otro ángulo, se edita `grados_por_paso` para que las vueltas de `--listar` cuadren. Eso no cambia los pulsos: los pulsos los mandan `pasos_por_mm` y la distancia.

`M114` al final de un canal que fue y volvió tiene que mostrar otra vez el origen (150 mm). El contador de pasos de X, Y y Z no cambia si el neto del movimiento es cero: es lo esperado.

## 8. Cómo leer una corrida

Cada línea sale así:

```text
===== X: G1 X10 F300 =====
ok P14 B3
```

`ok`, aunque venga con `P14 B3` o `P15 B3`, es una línea aceptada. La suite se detiene, suelta los motores con `M18` y no sigue con el canal siguiente si aparece alguno de estos textos:

- `Error`
- `Unknown command`
- `cold extrusion`
- `invalid extruder`

Al cierre quedan `G90`, `T0` y `M18`: posición absoluta, extrusor 0 seleccionado y motores sueltos.

`M122` confirma el driver. Para dar el canal por comunicado tienen que verse `connection... OK`, la corriente pedida, stealthChop, 16 micropasos y sin marcas de cortocircuito (`s2ga`, `s2gb`) ni sobretemperatura (`ot`). Una marca `ola` es carga abierta en la bobina A. E1 la mostró en la prueba del 5 de octubre: si ese eje no gira parejo en los dos sentidos, hay que revisar el plug y la continuidad de las dos bobinas antes de subir la corriente.

## 9. Pines de cada canal

ZBM, el segundo bornero de Z, va en paralelo con Z. No es un sexto eje.

| Canal | STEP | DIR | ENABLE | UART | DIAG |
|---|---|---|---|---|---|
| X | P2.02 | P2.06 | P2.01 | P1.10 | P1.29, X-STOP |
| Y | P0.19 | P0.20 | P2.08 | P1.09 | P1.28, Y-STOP |
| Z | P0.22 | P2.11 | P0.21 | P1.08 | P1.27, Z-STOP |
| E0 | P2.13 | P0.11 | P2.12 | P1.04 | P1.26, E0DET |
| E1 | P1.15 | P1.14 | P1.16 | P1.01 | P1.25, E1DET |

ENABLE es activo en bajo. Cada UART va a la dirección 0: un solo puente en el par UART/MS3 del zócalo, y MS1, MS2 y los puentes SPI sin colocar. DIAG del módulo entra en el zócalo. En X el firmware tiene sensorless compilado, con sensibilidad 100; esta suite no lo usa y no manda `G28`.

## 10. Qué no hace esta suite

- No homea. Un `G28` con el eje en vacío lo haría girar hasta ver un atasco, y en Y, Z, E0 y E1 el sensorless ni siquiera está compilado.
- No calienta.
- No sube una corriente por encima de `techo_ma`.
- No graba firmware. Para cambiar la inversión de DIR, los micropasos, la Rsense o el número de extrusores hay que editar el fuente en `firmware/Marlin` y copiar `firmware.bin` a la raíz de la microSD. El cargador de la SKR lo toma al reiniciar y lo renombra a `FIRMWARE.CUR`.
- `tonf enviar` sigue esperando un banner Grbl y no manda archivos a este Marlin. Un canal se mueve con su script (`scripts/prueba_motor_x.py`, `prueba_motor_y.py`, `prueba_motor_z.py`, `prueba_motor_e0.py`, `prueba_motor_e1.py`). La pasada completa es `scripts/suite.py`.

Los apuntes `Docs/2026-10-05_1233_comprobar-grblHAL.md` y `Docs/2026-10-05_1238_flashear-grblHAL.md` quedaron de un camino que no se usó. `Docs/2026-10-05_1241_marlin-instalado.md` describe el Marlin 2.0.5 que ya no está en la placa.
