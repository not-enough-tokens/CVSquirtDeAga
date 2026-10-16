"""Uso:
  python main.py                                  # Termux, cámara 0, 30 ciclos
  python main.py --images a.jpg b.jpg             # sin cámara (laptop / pruebas)
  python main.py --debug-mask                     # guarda la máscara de la pelota
  python main.py --ball-params ball_params.json   # umbrales calibrados
  python main.py --images a.jpg --arduino-port COM8   # laptop: manda cada resultado al Arduino
  python main.py --forever ...                    # sin límite de ciclos; reinicia la visión si el Arduino anuncia arranque
  (celular: ver phone/usb_launch.sh)
"""
import argparse
import sys
import time

import cv2

import link
from detectors import ArucoDetector, BallDetector, BallParams
from pipeline import ConsoleSink, stream, summarize
from sources import ImageFileSource, TermuxPhotoSource


def build(a):
    """Fuente y detectores nuevos. Se llama en cada sesión: así se relee ball_params.json."""
    source = ImageFileSource(a.images) if a.images else TermuxPhotoSource(camera=a.camera)
    bp = BallParams.from_json(a.ball_params) if a.ball_params else BallParams()
    if a.focal_px:
        bp.focal_px = a.focal_px
    ball = BallDetector(bp)
    return source, ball, [ArucoDetector(), ball]


def run_session(a, arduino, sinks, first):
    """Una sesión de visión. Devuelve (resultados, motivo de fin):
    'done' (n ciclos), 'restart' (el Arduino anunció arranque), 'error' (capturas fallidas), 'link' (USB caído)."""
    source, ball, detectors = build(a)
    if first and a.debug_mask:
        f = source.read()
        if f is not None:
            cv2.imwrite("ball_mask.png", ball.mask(f)[0])
            print("máscara -> ball_mask.png")
    results = []
    try:
        for _, r in stream(source, detectors):
            if arduino and arduino.take_boot():
                # el cuadro se capturó antes del arranque: describe al robot anterior, no se envía
                print("[sesión] reinicio del Arduino: cuadro descartado, visión reiniciada")
                return results, "restart"
            for s in sinks:
                s.send(r)
            results.append(r)
            if arduino and arduino.lost:
                print("[sesión] enlace USB caído")
                return results, "link"
            if not a.forever and len(results) >= a.n:
                return results, "done"
    except RuntimeError as e:
        print(f"[sesión] {e}")
        return results, "error"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="*")
    ap.add_argument("-n", type=int, default=30)
    ap.add_argument("--forever", action="store_true", help="sin límite de ciclos (ignora -n)")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--focal-px", type=float, default=None)
    ap.add_argument("--debug-mask", action="store_true")
    ap.add_argument("--ball-params", help="JSON generado por tools/calibrate_hsv.py")
    link.add_arguments(ap)
    a = ap.parse_args()

    arduino = link.sink_from_args(a)
    sinks = [ConsoleSink()] + ([arduino] if arduino else [])
    code, k = 0, 0
    try:
        while True:
            k += 1
            print(f"[sesión] #{k}")
            results, why = run_session(a, arduino, sinks, first=(k == 1))
            summarize(results)
            if why == "restart":
                continue
            if why == "error" and a.forever:
                print("[sesión] reintento en 5 s")
                time.sleep(5)
                continue
            code = {"done": 0, "error": 1, "link": 3}[why]
            break
    except KeyboardInterrupt:
        print("\nInterrumpido: Ctrl-C")
    finally:
        if arduino:
            arduino.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
