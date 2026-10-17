# CVSquirtDeAga — visión por computadora del robot (RoBorregos · Candidates 2026)

El celular (Pixel 8) hace de cámara y de cerebro de visión: toma una foto, detecta **marcadores ArUco**
y la **pelota naranja** (Pista B), y manda el resultado por USB a un Arduino, que lo muestra en un LCD 16x2
(y, más adelante, lo usará para decidir).

```
 Pixel 8 + Termux                                   Arduino (clon de Uno, CH340)
 ┌────────────────────────────┐   USB-C → hub → USB-B   ┌──────────────────────────┐
 │ termux-camera-photo        │ ─────────────────────▶ │ arduino/src/main.cpp     │
 │ ArUco + pelota (OpenCV)    │   "M,1,3,7,12,3\n"      │ parsea → LCD 16x2 (I2C)  │
 │ main.py / live.py          │ ◀───────────────────── │ (eco solo en `ledtest`)  │
 └────────────────────────────┘        115200 8N1       └──────────────────────────┘
        ▲ página de depuración (live.py) vista en la laptop por túnel SSH
```

## Estructura
| Ruta | Para qué sirve |
|---|---|
| `core.py`, `sources.py`, `pipeline.py` | Tipos (`Frame`, `Detection`, `FrameResult`), fuentes de imagen (cámara Termux / archivos) y el bucle único `stream()` / `run()` |
| `detectors/` | `aruco.py` (ArUco 4x4_50) y `ball.py` (pelota por HSV + morfología + circularidad) |
| `main.py` | Ciclo de detección por consola; `--arduino-port` (laptop) o `--arduino-fd` (celular) para enviar al Arduino |
| `live.py`, `onsite.py` | Demo en vivo: imagen anotada en una página web; clic sobre la pelota = calibración en sitio |
| `link.py` | Protocolo hacia el Arduino (`encode`) y transportes serie |
| `phone/` | Todo lo específico del celular: `usb_serial.py` (controlador CH340 sobre libusb1), `usb_launch.sh`, `probe_usb.py`, `led_test.py` |
| `arduino/` | Proyecto PlatformIO (abre **esta** carpeta en CLion/VS Code). Entornos: `uno` (firmware real), `scan` (escáner I2C), `lcdtest` (LCD con hd44780), `ledtest` (enlace USB solo con el LED) |
| `debug/` | `replay.py` (evalúa sobre un dataset etiquetado), `viz.py`, `web.py` |
| `tools/` | `capture_dataset.py`, `label_balls.py`, `calibrate_hsv.py` (calibración de los umbrales HSV) |
| `ball_params.json` | Umbrales HSV vigentes (calibrados con pelotas de ping-pong) |
| `_archive/` | Código antiguo conservado por si acaso |

`data/` (datasets) y `out/` (resultados) no se versionan.

## Uso rápido
**Laptop, sin cámara:** `python debug/replay.py data/ball_dataset --params ball_params.json --out out/replay`
(precisión/recall/F1 y galería de errores en `out/replay/index.html`).

**Celular, detección por consola:** `python main.py --ball-params ball_params.json -n 30`

**Celular, demo en vivo:** `python live.py`, y en la laptop `ssh -N -L 8000:127.0.0.1:8000 -p 8022 <usuario>@<ip>`;
abrir `http://127.0.0.1:8000/`. Clic sobre la pelota = recalibra HSV al instante; "Guardar" escribe `ball_params_site.json`.

**Enviar al Arduino desde el celular** (el Arduino debe llevar `uno`):
```
termux-usb -l                                  # el Arduino es uno de los dos (el otro es el hub)
termux-usb -r /dev/bus/usb/001/00N             # permiso, una vez
termux-usb -e ./phone/usb_launch.sh /dev/bus/usb/001/00N
```
`phone/usb_launch.cmd` dice qué se ejecuta (`main.py ...` o `live.py ...`). Tras desplegar archivos al celular
hay que repetir `chmod +x phone/*.py phone/*.sh`.

**Arranque en competencia (robot ElDefensor, Mega con `pistaA`/`pistaB` ya cargado):**
1. En el celular, abrir **IP Webcam** e iniciar el servidor (`http://127.0.0.1:8080/shot.jpg`; mucho más rápido
   que `termux-camera-photo`). `phone/usb_launch.cmd` ya lleva `--forever --camera-url ...`.
2. Encender el robot **quieto** (calibra el giroscopio). El LCD muestra `Espera vision 60` y `Ar:esperando`.
3. Conectar el USB y correr `bash phone/run.sh`: busca el CH340, abre el enlace (sin DTR: **no** reinicia el Mega)
   y manda detecciones. Con el primer mensaje válido el Mega pasa a `Arranca en 10 s` y luego corre la pista.
   Si en 60 s no llega nada, arranca sin visión (`ARRANQUE_ESPERA_VISION_MS` en `config.h` de ElDefensor).
4. Reinicio del Mega (lack of progress): anuncia `B` y `main.py` descarta el cuadro y reinicia la visión solo.
   Si el USB se cae, `run.sh` vuelve a buscar el Arduino cada 3 s.
Si IP Webcam no está abierta, las capturas fallan y `main.py --forever` reintenta cada 5 s.

**Firmware:** en `arduino/`, `pio run -e uno -t upload`; monitor: `pio device monitor --port COM8 --baud 115200 --echo`
(ejecútalo desde `arduino/` o pasa siempre `--port` y `--baud`).

**Calibrar con pelotas reales:** `tools/capture_dataset.py` → `tools/label_balls.py` →
`tools/calibrate_hsv.py --cv group --out ball_params_real.json` (ver el docstring de cada script).

## Protocolo celular → Arduino (v2)
Una línea ASCII por mensaje: `M,<bola>,<n>,<id1>,...,<idn>\n` (115200 baud).
`bola` = 1/0 (solo depuración), `n` = nº de ArUco (máx. 8), ids ordenados de más grande (cercano) a más pequeño, sin repetir.
El firmware descarta toda línea que no cuadre exacto y muestra "Sin enlace" tras 10 s sin datos válidos.
También acepta el formato antiguo `D,<bx>,<by>,<br>,<aid>`. La constante `MAX_IDS` está en `link.py` **y** en `arduino/src/main.cpp`: deben coincidir.

LCD: fila 1 `ArUco x3 Bola:si`; fila 2 `7 12 3` (con `+` si no caben todos).

## Hardware y particularidades
- Clon de Arduino con **CH340** (`1a86:7523`): no es CDC estándar; los baudios se fijan con peticiones de vendedor (`phone/usb_serial.py`).
- Android no tiene `/dev/ttyUSB*`: se usa `termux-usb` (entrega un descriptor) + libusb vía `python-libusb1`. Requiere Termux:API instalada desde la misma fuente que Termux.
- Por defecto no se activa DTR, así que abrir el puerto **no reinicia** el Arduino.
- LCD I2C en `0x27` (PCF8574). Si no se ve texto: contraste del potenciómetro, soldaduras entre el backpack y el LCD, o `scan`/`lcdtest`.

## Qué está comprobado y qué no
**Comprobado:** detección de pelota (F1 0.935 en validación cruzada por escenas, con el dataset de ping-pong de Roboflow; precisión ≈ 99 %, recall ≈ 88 %) · ArUco múltiples · enlace celular → Arduino → LCD con detecciones reales · eco Arduino → celular (`ledtest`, 4/4) · lógica del firmware en simulación de PC.

**Pendiente:**
- Calibrar con las pelotas reales (golf: `diameter_m` 0.042; las de ping-pong miden 0.040) y confirmar el color del piso de la Pista B.
- Arranque desde un interruptor físico y modo petición-respuesta (`?` → `M,...`), con supervisor en Termux que se reconecte si el USB parpadea.
- Alimentación del Arduino y del celular a la vez (evitar corriente de vuelta por el USB).
- Pelotas tocándose se fusionan en una sola mancha y se rechazan por circularidad (falta separar con transformada de distancia + watershed).
- El dataset de entrenamiento usa imágenes estiradas a 640×640 (círculos → elipses); los umbrales toleran razón ≈ 1.5.

## Dependencias
Celular (Termux): Python con OpenCV (`cv2`) y numpy ya instalados (ver cómo se instalaron en tu Termux), más `pkg install termux-api libusb` y `pip install libusb1`.
Laptop: `pip install opencv-python numpy pyserial`. Firmware: PlatformIO (las librerías se descargan solas).
