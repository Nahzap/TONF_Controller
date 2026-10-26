# Avances del banco — 5 de octubre de 2026, 18:25

Nota local. No entra al repositorio. El manual que se publica es `README.md`. El commit de este estado se llama `2c`.

## Qué quedó verificado

La suite informa por la terminal mientras corre, y los cinco motores se mueven: X, Y, Z, E0 y E1.

E0 y E1 conservan ese nombre. E0 es la herramienta `T0` y E1 es la herramienta `T1`. Los dos se desplazan con la letra E de G-code (`G1 E…`, `M906 T0 E…`, `M906 T1 E…`, `M914 T0 E…`, `M914 T1 E…`). La placa que está grabada los trata así. Un intento de pasarlos a las letras U y V no se grabó y se revirtió: con esas letras los zócalos no recibían pasos.

## Terminal

Cada comando se imprime antes de enviarse y la respuesta de la placa sale en cuanto llega, incluido `echo:busy` durante el giro. La suite abre con el puerto y los avisos, luego marca el grupo (`----- ajuste -----`, `----- X -----`, `----- E0 -----`, `----- E1 -----`, `----- cierre -----`) y debajo cada orden (`===== G1 E10 F300 =====`).

Los programas de un solo canal hacen lo mismo y nombran el canal al arrancar (`Canal E0.`, `Canal E1.`).

## StallGuard

Los cinco TMC2209 llevan umbral 100.

- X, Y y Z: `M914 X100`, `M914 Y100`, `M914 Z100`. Esos tres pueden homear con `G28`. La suite no manda `G28`.
- E0 y E1: `M914 T0 E100` y `M914 T1 E100`. El umbral queda en el driver. Marlin no homea un extrusor.

El firmware grabado es Marlin 2.1.2, máquina «TONF SKR», compilado el 5 de octubre de 2026 a las 17:44:30, binario de 206024 bytes. Después de esa grabación la EEPROM dejó Y y Z en umbral 0; la suite vuelve a escribir 100 y guarda con `M500`.

## Corrientes y secuencia

| Canal | Corriente | Pasos/mm | Comando de movimiento |
|---|---|---|---|
| X | 450 mA | 80 | `G1 X` |
| Y | 800 mA | 80 | `G1 Y` |
| Z | 800 mA | 400 | `G1 Z` |
| E0 | 800 mA | 95 | `T0` y `G1 E` |
| E1 | 800 mA | 95 | `T1` y `G1 E` |

El tope de la suite es 800 mA. La secuencia en vacío sigue siendo 10 mm a F300, regreso, 40 mm a F600, regreso, 40 mm a F1800, regreso, con `M400` entre tramos. No hay home. `M302 S0` permite mover E0 y E1 en frío. `M412 S0` deja apagado el sensor de filamento.

El tramo de F1800 pide 30 mm/s. Z queda recortado a 20 mm/s y E a 25 mm/s.

## Respaldo y pruebas del programa

`BKP/` tiene la misma copia que `scripts/prueba_motor_*.py`. Los tests del programa, sin abrir la placa, son 24 y pasaron.

## Qué no cambió en la placa

No se grabó un firmware nuevo en esta pasada. La Rsense compilada de X, Y, Z y E0 sigue distinta de los 0,11 Ω del módulo. Y puede marcar carga abierta en la bobina B y E1 en la bobina A; si el giro no es parejo, se revisa el plug.
