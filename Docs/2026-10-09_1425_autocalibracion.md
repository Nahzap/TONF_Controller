# Autocalibración de un eje

9 de octubre de 2026, 14:25.

Al abrir el monitor el carro de ese eje está en el mínimo físico. El programa pregunta cuál eje calibrar. Aplica corriente y ordena un paso hacia arriba. Si ese paso no sube, el sentido es el contrario. Cuando llega al máximo ocurre el mismo atasco; el sentido ya quedó registrado, así que retrocede el margen, va al punto medio y queda habilitado. El detalle se guarda en un json. Al reiniciar, si ese json sigue valiendo, no se repite la rutina.

Los números de esa búsqueda no están en el programa. Están en `config/banco.toml`, tabla `[calibracion]`, y en el canal.

## Números

| Campo | Qué decide |
|---|---|
| `calibracion.paso_mm` | Cada intento, en mm |
| `calibracion.avance_mm_min` | La F de la búsqueda, y la de `M`, `P` y `TOPE` cuando la orden no trae F |
| `calibracion.margen_mm` | Lo que se deja libre en cada extremo |
| `calibracion.sonda_mm` | Máximo de la orden `P` |
| `calibracion.sin_topes_mm` | Máximo de cada `M` si se confirmó `LIM` sin medir el metal |
| `canales.*.sentido` | Sentido del primer intento. `1` o `-1` |
| `canales.*.corriente_ma` | Corriente que se aplica para subir |
| `canales.*.pasos_por_mm` | Pasos del planificador. Si el json no coincide, se calibra de nuevo |
| `canales.*.sensibilidad_stall` | Umbral `M914` |
| `canales.*.sigilo` | Al buscar se usa spreadCycle. Al terminar se vuelve a este chopper |
| `limites_mm` | Si el máximo no aparece dentro de esa caja, se corta. No es la medida del riel |
| `secuencia.*.espera_fin_s` | Espera máxima de cada tramo |

El avance de calibración no puede pasar el `M203` de ese eje (`avances_maximos_mm_s` por 60). El paso no puede ser menor que un paso del planificador.

## Al abrir

```text
Eje a calibrar (X, Y o Z). CERRAR sale. X! repite la rutina:
```

`X`, `Y` o `Z` calibran ese eje, o leen su json si ya existe. `X!` repite la rutina aunque el json esté. `CERRAR` suelta los motores y sale. E0 y E1 no tienen riel: la pregunta no los acepta.

El eje tiene que haber contestado por UART, sin cortocircuito ni sobretemperatura. Carga abierta se rechaza, salvo `FORZAR` de una sesión anterior; en el arranque todavía no hubo `FORZAR`.

## La rutina

El carro está apoyado en el mínimo, sin haber subido.

1. Se escribe la corriente del canal, spreadCycle y el umbral de atasco. `G92` deja ese punto en 0. `M119` tiene que estar abierto. Si el final ya está activo, no se mueve.
2. Se ordena un paso en el sentido del canal. `M119` mira `{eje}_min` y `{eje}_max`. `TRIGGERED` es atasco.
3. Si ese primer paso atasca, no subió. Se invierte el sentido, se vuelve a poner 0 y se prueba un paso al otro lado. Si ese tampoco sube, se manda `M410` y `M18`, y no se guarda nada.
4. Mientras sube, se sigue de a un paso. El atasco siguiente es el máximo. La posición que se guarda es la última que quedó libre, no el paso que chocó.
5. Si esa longitud no deja sitio para el margen en los dos extremos, se suelta y no se guarda.
6. Si no aparece atasco antes de agotar la caja de `limites_mm`, se corta para no seguir empujando.
7. Se retrocede el margen, lejos del metal, y se va al punto medio de la longitud medida.
8. Se restaura el chopper del canal y se habilita el eje con `M17`. Queda bloqueado ahí.

El cero lógico es el mínimo físico. Un `M` con pasos positivos va hacia el máximo, aunque el sentido de Marlin haya quedado en `-1`.

## El json

Se escribe en `config/calibracion/X.json` (o Y, o Z), al lado de `banco.toml`. Esa carpeta no entra al repositorio.

Guarda el eje, la fecha, los pasos/mm, el sentido medido, la corriente, el margen, el mínimo y el máximo mecánicos, el tramo de trabajo, la longitud, el punto medio, los pasos entre topes, el umbral de atasco y que el eje quedó bloqueado.

Al volver a abrir el monitor se pregunta el eje. Si el json está y `pasos_por_mm` coincide con el canal, no se recorre el riel: `G92` declara el punto medio y `M17` lo habilita otra vez. Abrir el COM reinicia la placa y suelta los motores un instante; el programa no mueve el carro para buscar el medio, lo declara y lo traba. Si alguien corrió el eje a mano, ese json ya no es cierto: `X!` repite la rutina, o `ANULAR X` borra el archivo.

`CERRAR`, `PARAR` y `SOLTAR` sueltan el eje. La próxima apertura, con el json presente, lo vuelve a habilitar en el punto medio.

## Cómo abrirlo

```powershell
.\.venv\Scripts\python.exe .\scripts\menu.py
```

El carro del eje elegido tiene que estar en el mínimo antes de contestar la pregunta.
