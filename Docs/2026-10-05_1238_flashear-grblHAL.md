# Sustituir Marlin por grblHAL — 2026-10-05 12:38

La placa que está en COM3 (`1D50:6029`) ejecuta Marlin. grblHAL no se instala encima: el bootloader borra ese programa y escribe el nuevo en la misma zona de flash, a partir de `0x4000`. El bootloader de la microSD se queda. Marlin vuelve solo si más adelante se graba otro `firmware.bin` de Marlin por el mismo camino. Conviene guardar una copia de ese binario antes de sustituirlo.

El Web Builder de grblHAL (https://svn.io-engineering.com:8443/) no compila este microcontrolador. Sus drivers son iMXRT, STM32, ESP32, SAM3X8E, RP2040 y un simulador. Para la SKR V1.4 Turbo el proyecto oficial es [grblHAL/LPC176x](https://github.com/grblHAL/LPC176x), compilado con MCUXpresso.

## Compilar el binario correcto

1. Instalar [MCUXpresso IDE](https://www.nxp.com/design/design-center/software/development-software/mcuxpresso-software-and-tools-/mcuxpresso-integrated-development-environment-ide:MCUXpresso-IDE) y clonar el repositorio con sus submódulos:

```text
git clone --recurse-submodules https://github.com/grblHAL/LPC176x.git
```

2. En `src/my_machine.h` dejar activa una sola placa y el TMC2209. `USB_SERIAL_CDC` ya está en 1:

```c
#define BOARD_BTT_SKR_14_TURBO
#define TRINAMIC_ENABLE      2209
#define TRINAMIC_R_SENSE      110
```

`TRINAMIC_R_SENSE` está en miliohmios. 110 corresponde al módulo BTT de 0,110 Ω. No actives a la vez `BOARD_BTT_SKR_E3_TURBO`: esa variante es otra placa, con los drivers soldados, y el propio archivo la marca como no verificada.

3. Importar el proyecto en MCUXpresso y construir la configuración **BL_0x4000**. Esa configuración enlaza el programa detrás del bootloader de 16 KiB y genera `firmware.bin`. Un Debug o Release normal no sirve para la microSD: arrancaría en la dirección 0 y pisaría el bootloader, o el bootloader no lo cargaría.

4. El archivo queda en la carpeta de esa configuración. El nombre que hay que copiar es exactamente `firmware.bin`.

## Grabar la microSD

La placa se apaga antes de tocar la tarjeta.

1. Jumper **5V SEL** entre **+5V** y **VDD**. En esa posición la lógica sale de la fuente, no del USB.
2. Cable USB desconectado. Si el USB alimenta la lógica, en esta familia el bootloader a veces no corre.
3. MicroSD FAT32, MBR. `firmware.bin` en la raíz, no dentro de una carpeta.
4. Tarjeta en el lector de la placa. Fuente de 12–24 V. Pulsar **RESET**.
5. Esperar unos diez segundos, quitar alimentación y sacar la SD.

Comprobación de que grabó: el archivo se llama `firmware.cur`. Si sigue llamándose `firmware.bin`, el bootloader no lo tomó (nombre, sistema de archivos o jumper).

No hay botón BOOT. No se flashea por DFU en estas SKR: el pin que el bootloader viejo usaba para DFU es el enable de E0.

## Comprobar que ahora es grblHAL

Volver a poner el USB. En `D:\TONF_Controller`:

```powershell
.\.venv\Scripts\python.exe -m tonf puertos
.\.venv\Scripts\python.exe -m tonf enviar pieza.nc --comprobar
```

La segunda orden abre el COM, espera el banner y solo entonces manda `$C` y el G-code. Con grblHAL tiene que terminar en `Líneas aceptadas: N de N`. Con el Marlin actual se detiene y no envía el archivo; eso fue lo que ocurrió a las 12:33, con salida 1.

El movimiento de verdad es la misma orden sin `--comprobar`, después de que la comprobación haya aceptado todas las líneas, y con la fuente de motores y los drivers ya revisados.
