# Cómo comprobar grblHAL — 2026-10-05 12:33

Terminal usada: PowerShell, carpeta `D:\TONF_Controller`.
Python del entorno: `.venv\Scripts\python.exe`.

## Resultado de esta pasada

La placa está en **COM3** (`1D50:6029`). El programa de envío **no mandó el G-code**. El puerto no contestó con un banner `Grbl` o `grblHAL`, así que el archivo se quedó en el PC. Hasta que la microSD tenga el `firmware.bin` de grblHAL, esta comprobación tiene que terminar así.

Salida real:

```text
---- PUERTOS ----
COM3    1D50:6029    Dispositivo serie USB (COM3)

---- VISTA ----
G0 X0 Y0
G1 X10 Y2 F300

---- ENVIAR COMPROBAR ----
Un solo USB serie coincide con LPC/Marlin/Klipper.
Abierto COM3 a 250000 baudios.
El puerto no presentó un banner Grbl/grblHAL. No se envió el archivo.
EXIT 1
```

`EXIT 1` aquí es la protección: el firmware que hay ahora no es grblHAL.

## Tres comprobaciones, en este orden

Abre una terminal en `D:\TONF_Controller` y ejecuta estas líneas tal cual.

### 1. Ver que el entorno responde

```powershell
.\.venv\Scripts\python.exe -m tonf firmware
.\.venv\Scripts\python.exe -m tonf puertos
```

Tiene que listar un COM. Si no hay ninguno: jumper **5V SEL** entre **USB** y **+5V**, cable de datos, LED rojo **D5** encendido.

### 2. Ver el G-code que saldría, sin tocar la placa

Sustituye `pieza.nc` por tu archivo.

```powershell
.\.venv\Scripts\python.exe -m tonf enviar pieza.nc --vista
```

Imprime cada línea ya limpia (sin comentarios ni líneas vacías). No abre el USB. En la pasada de las 12:33, de un bloque de prueba salieron solo `G0 X0 Y0` y `G1 X10 Y2 F300`.

### 3. Pedir a grblHAL que analice el archivo sin mover motores

```powershell
.\.venv\Scripts\python.exe -m tonf enviar pieza.nc --comprobar
```

Eso envía `$C` (modo comprobación de grbl) y después el archivo. grblHAL responde `ok` o `error:` por línea y no genera pasos.

Hoy el paso 3 se detiene antes de la primera línea, porque el banner no es Grbl. Cuando el firmware esté grabado, la misma orden tiene que terminar en `Líneas aceptadas: N de N` y código de salida 0.

## Qué tiene que ocurrir en la placa antes del paso 3

El binario no sale del Web Builder: ese generador no incluye el LPC1769. El procedimiento de grabado está en `Docs/2026-10-05_1238_flashear-grblHAL.md`. Cuando `firmware.cur` confirme que grabó, se repite el paso 3.

El movimiento real es la misma orden sin `--comprobar`, y solo después de que el paso 3 haya aceptado todas las líneas. Con los drivers aún sin montar, esa orden no debe usarse para “ver si gira”.
