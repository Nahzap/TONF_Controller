# Protocolo serial de ejes

9 de octubre de 2026, 13:53.

El arranque del monitor es la autocalibración: el carro en el mínimo, un sentido, el máximo, el punto medio y un json. Está en `Docs/2026-10-09_1425_autocalibracion.md`. Paso, avance, margen, sonda y tope sin medición salen de `[calibracion]` en `config/banco.toml`. Este texto es el de las órdenes manuales, una vez que el eje ya tiene límites.

Este menú mueve un motor por el puerto serie y se niega a mandar un paso que salga del mínimo o del máximo. Hoy el único motor conectado es X. Y, Z, E0 y E1 quedan bloqueados hasta que alguien los permita, y E0 y E1 no tienen riel en este menú.

El código está partido. Cada archivo decide una cosa y no abre el puerto, salvo `runner.py`.

| Módulo | Decide |
|---|---|
| `src/tonf/manual/drivers.py` | Si el driver contestó por UART y si hay carga abierta, cortocircuito o sobretemperatura |
| `src/tonf/manual/steps.py` | Pasos del planificador ↔ milímetros |
| `src/tonf/manual/window.py` | Rechazar un destino fuera del mínimo o del máximo, y la sonda más larga que `calibracion.sonda_mm` |
| `src/tonf/manual/limits_cmd.py` | `LIM` y `MARGEN`: mínimo, máximo y longitud útil |
| `src/tonf/manual/travel.py` | `P`, `TOPE` y `M`: o arma un `G1` absoluto, o no envía nada |
| `src/tonf/manual/origin.py` | `REF` y `POS` |
| `src/tonf/manual/axis_cmd.py` | Qué eje está permitido, `FORZAR` y `ANULAR` |
| `src/tonf/manual/grammar.py` | Leer la línea que escribe el operador |
| `src/tonf/manual/startup.py` | Ajuste inicial, sin movimiento |
| `src/tonf/manual/reply.py` | Qué hacer con la respuesta de la placa |
| `src/tonf/manual/status.py` | El texto de `ESTADO` |
| `src/tonf/manual/session.py` | El estado de la sesión y el despacho de la orden |
| `src/tonf/manual/model.py` | Los datos que comparten los módulos |
| `src/tonf/manual/runner.py` | Abrir COM, mandar la línea ya aceptada y soltar motores si la placa rechaza |

## Cómo se mueven los cinco ejes hoy

La placa es la BTT SKR V1.4 Turbo con Marlin 2.1.2, máquina «TONF SKR». El host abre COM3 a 115200 baudios, una línea ASCII y un salto de línea. Abrir el puerto reinicia el LPC1769 porque Windows afirma DTR.

No hay encoder. `M114` es la posición que Marlin cree haber mandado. Un paso pedido no es una posición medida.

| Canal | Orden de movimiento | Pasos/mm | Caja compilada | Corriente de la suite | DIR compilado |
|---|---|---|---|---|---|
| X | `G90`, `G92 X`, `G91`, `G1 X` | 80 | 4…319 mm | 450 mA | invertido |
| Y | `G90`, `G92 Y`, `G91`, `G1 Y` | 80 | 2…306 mm | 800 mA | invertido |
| Z | `G90`, `G92 Z`, `G91`, `G1 Z` | 400 | 0…400 mm | 800 mA | directo |
| E0 | `T0`, `M83`, `G92 E`, `G1 E` | 95 | no tiene riel | 800 mA | invertido |
| E1 | `T1`, `M83`, `G92 E`, `G1 E` | 95 | no tiene riel | 800 mA | directo |

Esos pasos/mm son los de `M92`: micropasos del planificador. En X, 80 pasos son 1 mm y un paso son 0,0125 mm. Con 1,8 ° y 16 micropasos hay 3200 pulsos por vuelta. El menú usa esa misma cuenta. Un `M X 800` son 800 pasos lógicos, o sea 10 mm, no 800 vueltas.

La suite de `scripts/suite.py` recorre una secuencia fija en vacío. Antes de abrir el puerto comprueba que X, Y y Z no salgan de `limites_mm` en `config/banco.toml`. Esa comprobación vale para la secuencia escrita en el archivo. No vigila una orden suelta escrita a mano en un terminal serie.

Marlin tiene finales de software compilados en esa misma caja. Los aplica cuando el eje está referido por home. Este banco no manda `G28`: un home en vacío haría girar el motor hasta un atasco. Sin home, esa caja no frena un `G1`. El menú frena antes, en el host.

Tampoco hay final de carrera mecánico en uso. El pin DIAG del TMC2209 ocupa el pin de fin de carrera. `M119` no mide el extremo del riel.

## Por qué el riel quema el motor

El extremo del riel es un tope de metal. Si el motor sigue recibiendo pasos contra ese tope, el eje no avanza y la bobina sigue con corriente. No hay encoder que corte el movimiento. A 450 mA en X, un atasco calienta el motor.

La caja 4…319 mm es un número compilado. No es la medida del riel que está armado ahora. Si el carro llega al metal antes de ese número, la caja compilada no lo salva.

El menú solo manda pasos dentro de un mínimo y un máximo de trabajo. Esos dos números tienen que quedar dentro del metal, con el margen de `[calibracion]`. La medida la hace la autocalibración al abrir. `P` y `TOPE` siguen sirviendo para marcar un extremo a mano, después de `ANULAR`.

## Qué hay que tener puesto

Fuente de 12 V en VMOT, puente 5V SEL entre +5V y VDD, USB solo en datos, y el motor X enchufado en el orden `1B 1A 2A 2B`. Para calibrar, el carro de ese eje está en el mínimo físico. Para una orden manual posterior, tiene que estar dentro del tramo ya medido.

Y, Z, E0 y E1 no deben estar acoplados a una carga. El menú no les manda `M906` ni `G1`. Al mover X suelta Y, Z y E con `M18 Y Z E`.

## Cómo abrirlo

Desde la carpeta del proyecto:

```powershell
.\.venv\Scripts\python.exe .\scripts\menu.py
```

Lo mismo, con otro puerto si hace falta:

```powershell
.\.venv\Scripts\python.exe -m tonf menu --puerto COM3 --baud 115200
```

El programa abre el COM, espera el arranque y escribe en la terminal cada orden Marlin entre `=====` y la respuesta de la placa. El prompt del operador es `tonf>`. Lo que se escribe ahí es el protocolo de este documento. No es G-code.

Al arrancar, sin mover motores, manda `M115`, `M302 S0`, `M412 S0`, `M203`, `M92`, `G90`, `M18` y `M122`.

## Protocolo

Una orden por línea. Mayúsculas o minúsculas. Los números en mm aceptan punto o coma. Los pasos son un entero con signo, sin decimales. El eje, si va, es `X`, `Y`, `Z`, `E0` o `E1`.

```text
orden      = ayuda | id | estado | usar | permitir | bloquear | forzar
           | ref | sonda | tope | margen | lim | manual | pos
           | anular | parar | soltar | cerrar

ayuda      = "?" | "AYUDA"
id         = "ID"
estado     = "ESTADO"
usar       = "USAR" eje
permitir   = "PERMITIR" eje
bloquear   = "BLOQUEAR" eje
forzar     = "FORZAR" eje
ref        = "REF" eje mm
sonda      = "P" [eje] pasos
tope       = "TOPE" ["MIN" | "MAX"] | "TOPE" eje ["MIN" | "MAX"]
margen     = "MARGEN" mm
lim        = "LIM" eje minimo maximo ["CONFIRMAR"]
manual     = "M" [eje] pasos [avance]
avance     = "F" mm_por_min | "F" mm_por_min
pos        = "POS"
anular     = "ANULAR" eje
parar      = "PARAR"
soltar     = "SOLTAR"
cerrar     = "CERRAR"

eje        = "X" | "Y" | "Z" | "E0" | "E1"
pasos      = entero distinto de cero
mm         = número
minimo     = número
maximo     = número
```

`M X 800` y `M X 800 F300` son la misma orden si el avance del archivo es 300; la segunda fija el avance. `F` y el número, juntos o separados, también valen. Sin `F`, `M`, `P` y `TOPE` usan `calibracion.avance_mm_min`. `P` no acepta otra F.

### Respuestas

| Prefijo | Significado |
|---|---|
| `OK` | La orden quedó aplicada |
| `AVISO` | Hay un dato que el operador tiene que leer antes de seguir |
| `RECHAZADO` | No se movió el motor por esa orden |
| `MOTOR` | Estado de un driver |

Una orden rechazada de movimiento no lleva `G1`. El rechazo dice cuántos pasos caben en ese sentido.

### Reconocer motores: `ID`

`ID` manda `M122` y escribe una línea por canal:

```text
MOTOR X uart=OK permitido=sí fallas=ninguna pasos/mm=80
MOTOR Y uart=Error: All LOW permitido=no fallas=ninguna pasos/mm=80
```

| Campo | Qué significa |
|---|---|
| `uart=OK` | El TMC2209 de ese zócalo contestó |
| `uart=Error: All LOW` o `no apareció en M122` | Ese driver no está para mover |
| `permitido=sí` | El operador autorizó ese eje. Al abrir, solo X |
| `fallas=ola` o `olb` | Carga abierta en una bobina. El menú no mueve ese eje |
| `fallas=cortocircuito` o `sobretemperatura` | El menú no mueve ese eje |

`uart=OK` quiere decir que el módulo driver contestó. No demuestra que el motor esté enchufado. Por eso Y y Z nacen bloqueados aunque su driver responda. `PERMITIR Y` solo se usa cuando ese motor está conectado y libre.

`FORZAR X` ignora `ola` y `olb` de X durante esta sesión. No ignora un cortocircuito ni una sobretemperatura, y no inventa un driver que no contestó. En este banco la bobina abierta a veces es una marca falsa; si el eje no gira, el plug se revisa antes de forzar.

E0 y E1 se listan en `ID`. `PERMITIR E0` se rechaza: no tienen `limites_mm`. Este menú no los mueve.

### Definir mínimo, máximo y longitud: `LIM`

La longitud útil es `máximo − mínimo`. `ESTADO` la imprime en mm y en pasos.

`LIM` exige que el eje ya tenga `REF` y que la posición actual quede dentro del tramo. El tramo tiene que entrar en la caja compilada. En X esa caja es 4…319 mm. Un `LIM X 0 400` se rechaza.

Hay dos formas de dejar el tramo activo:

1. Marcar el metal con `TOPE MIN` y `TOPE MAX`. Después `LIM` solo puede achicar ese tramo, no agrandarlo.
2. `LIM X 20 280 CONFIRMAR`. Acepta el tramo sin haber visto los topes. Cada `M` queda cortado a 10 mm (800 pasos en X) hasta que existan los dos topes mecánicos.

`LIM X 20 280` sin `CONFIRMAR` solo guarda la propuesta. `M` sigue bloqueado.

### Buscar el metal: `REF`, `P` y `TOPE`

`REF X 150` declara que el carro, quieto y libre, está en 150 mm lógicos. Manda `G92`. No mueve el motor. 150 tiene que caer dentro de la caja compilada. Si ya hay límites, hay que `ANULAR X` antes de otra referencia.

El número 150 no mide el riel. Es el origen lógico, el mismo que usa la suite. El carro tiene que estar de verdad en un hueco libre cuando se escribe.

`P` es la sonda, para caminar hacia el metal:

- Como máximo `calibracion.sonda_mm` por orden. Con el archivo de hoy, en X son 80 pasos. `P X 8` son 0,1 mm.
- El avance es `calibracion.avance_mm_min`.
- No entra en un límite de trabajo ya marcado.
- No sale de la caja compilada.

`TOPE MIN` marca el extremo de coordenada baja. `TOPE MAX` marca el de coordenada alta. El menú guarda esa posición como tope mecánico y retrocede `calibracion.margen_mm`, salvo que esta sesión lo haya cambiado con `MARGEN`. El límite de trabajo queda en el punto ya retrocedido, no contra el metal.

`MARGEN` pide un número mayor que 0. El cambio vale para el próximo `TOPE` de esta sesión. No reescribe el archivo.

Después de `TOPE MIN`, una sonda hacia ese metal se rechaza: el margen no se vuelve a cruzar.

Cuando los dos topes están marcados y el mínimo de trabajo es menor que el máximo, `M` puede recorrer todo el interior. El destino puede ser el límite de trabajo. No puede pasarlo.

### Mover a mano: `M`

```text
M X 800
M X -160
M X 800 F300
M 80
```

El signo positivo suma milímetros a la posición lógica. El signo negativo resta. En X, con `INVERT_X_DIR` compilado, el sentido físico del positivo es el de la máquina ya grabada. La primera sonda para aprender el sentido es `P X 8` o `P X -8`, mirando el carro.

`M` sale solo si se cumplen todas:

1. El eje está permitido.
2. `ID` lo vio con UART en OK, sin cortocircuito ni sobretemperatura.
3. No hay carga abierta, o se usó `FORZAR` en esta sesión.
4. Hay `REF` y la posición no está incierta.
5. Hay mínimo y máximo de trabajo.
6. El destino cae dentro de ese tramo.
7. Si los topes no se marcaron en el metal y el tramo vino de `CONFIRMAR`, la orden no pasa de 10 mm.

Si falta cualquiera, la respuesta es `RECHAZADO` y no hay `G1`.

El avance de `M`, si se escribe, va de 60 a 600 mm/min. Si no se escribe, son 300 mm/min.

Traducción de un `M X 800` con X en 150 mm, 80 pasos/mm y ventana que contiene 160 mm:

```text
G90
G1 X160 F300
M400
M114
M18 Y Z E
```

`M400` espera a que el tramo termine. `M114` tiene que coincidir con el destino a 0,05 mm. Si no coincide, la posición queda incierta y el siguiente `M` se rechaza hasta `POS`.

La primera `REF` o el primer movimiento de ese eje también manda, una sola vez, `M906 X450`, `M569 X S1` y `M914 X100`. Son los valores de `config/banco.toml`. No se manda `M500`.

### Parar y soltar

| Orden | Qué manda | Efecto en el estado |
|---|---|---|
| `PARAR` | `M410` y después `M18` | Corta el plan y suelta todos los motores. La posición queda por confirmar con `POS` |
| `SOLTAR` | `M18` | Suelta el torque. Igual deja la posición por confirmar |
| `ANULAR X` | `M18` | Borra referencia, topes y límites de X |
| `CERRAR` | `M18` | Suelta y sale del menú |
| Ctrl+C durante un envío | `M410` y `M18` | Suelta y deja el prompt |

`M114` no ve un carro movido a mano. Si se soltó el motor y alguien corrió el eje, `ANULAR` y una `REF` nueva. Si `POS` lee una posición fuera del mínimo y el máximo, no hay movimiento de rescate automático: se suelta, se aparta el carro a mano del metal, se anula y se referencia otra vez.

`POS` manda `M114` y, si el valor cae dentro de los límites, levanta la incertidumbre.

`ESTADO` no habla con la placa. Muestra selección, margen, motores, posición, límites, longitud y topes mecánicos.

`?` repite la lista corta de órdenes.

## Recorrido con solo X conectado

El arranque no es este recorrido. El carro se deja en el mínimo y el monitor calibra. Ver `Docs/2026-10-09_1425_autocalibracion.md`.

`P` y `TOPE` quedan para marcar un extremo a mano después de `ANULAR X`, que también borra el json.

Para achicar el tramo ya marcado, por ejemplo dejar X entre 30 y 200 mm con el carro dentro:

```text
LIM X 30 200
```

Esa orden no mueve. No puede salir del tramo que marcaron los topes.

Después de `ANULAR`, si no se va a medir el metal en esta sesión:

```text
REF X 150
LIM X 20 280 CONFIRMAR
```

Cada `M` de esa sesión queda en `calibracion.sin_topes_mm` hasta `TOPE MIN` y `TOPE MAX`. Esos 20 y 280 tienen que ser interiores al riel real. La caja compilada 4…319 no sustituye esa medida.

## Ejemplo

Arranque, ya con `MOTOR X uart=OK`. El carro está libre.

```text
tonf> REF X 150
===== M906 X450 =====
ok
===== M569 X S1 =====
ok
===== M914 X100 =====
ok
===== G90 =====
ok
===== G92 X150 =====
ok
OK referencia X en 150 mm. El carro tiene que estar libre ahí.

tonf> P X -80
===== G90 =====
ok
===== G1 X149 F300 =====
ok
===== M400 =====
ok
===== M114 =====
X:149.00 Y:0.00 Z:0.00 E:0.00 Count X:0 Y:0 Z:0
ok
===== M18 Y Z E =====
ok
OK X ahora en 149 mm.

tonf> M X 800
RECHAZADO X no tiene mínimo y máximo. Márquelo con TOPE MIN y TOPE MAX, o use LIM con CONFIRMAR.
```

Ese `M` no produjo `G1`.

Con la ventana confirmada y el carro otra vez en 150 mm lógico, dentro de 20…280:

```text
tonf> LIM X 20 280 CONFIRMAR
OK X limitado a 20…280 mm, longitud 260 mm.
AVISO esos topes no se midieron en el riel. Cada M queda cortado a 10 mm hasta TOPE MIN y TOPE MAX.

tonf> M X 800
===== G90 =====
===== G1 X160 F300 =====
===== M400 =====
===== M114 =====
===== M18 Y Z E =====
OK X ahora en 160 mm.

tonf> M X 801
RECHAZADO sin los dos topes mecánicos cada M se corta a 10 mm (800 pasos en X). Esta orden pide 10.0125 mm.

tonf> M X 10401
RECHAZADO el destino 280.0125 mm pasa el máximo 280 mm. En este sentido caben 9600 pasos. No se envió el movimiento.
```

`9600` pasos es lo que cabe desde 160 mm hasta 280 mm a 80 pasos/mm. La orden que se pasa no se recorta sola: o cabe entera, o no se envía.

## Qué no hace este menú

- No manda `G28`, `G0`, `M104`, `M109`, `M140`, `M190` ni `M211 S0`.
- No apaga los finales de software de Marlin. Tampoco cuenta con ellos: sin home no protegen el riel.
- No mueve E0 ni E1.
- No mueve Y ni Z hasta `PERMITIR`, y ese permiso no crea un riel. Siguen haciendo falta `ID`, `REF` y límites.
- No graba EEPROM.
- La medida del riel al abrir es la autocalibración. `P` queda para un extremo marcado a mano, con el tope de `calibracion.sonda_mm`.

Las pruebas de este protocolo, sin abrir la placa, están en `tests/test_manual_drivers.py`, `tests/test_manual_steps.py`, `tests/test_manual_session.py`, `tests/test_manual_runner.py` y `tests/test_manual_calibrate.py`.
