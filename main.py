"""Uso:
  python main.py                                  # Termux, cámara 0, 30 ciclos
  python main.py --images a.jpg b.jpg             # sin cámara (laptop / pruebas)
  python main.py --debug-mask                     # guarda la máscara de la pelota
  python main.py --ball-params ball_params.json   # umbrales calibrados
"""
import argparse

import cv2

from detectors import ArucoDetector, BallDetector, BallParams
from pipeline import ConsoleSink, run, summarize
from sources import ImageFileSource, TermuxPhotoSource


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="*")
    ap.add_argument("-n", type=int, default=30)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--focal-px", type=float, default=None)
    ap.add_argument("--debug-mask", action="store_true")
    ap.add_argument("--ball-params", help="JSON generado por tools/calibrate_hsv.py")
    a = ap.parse_args()

    source = ImageFileSource(a.images) if a.images else TermuxPhotoSource(camera=a.camera)
    bp = BallParams.from_json(a.ball_params) if a.ball_params else BallParams()
    if a.focal_px:
        bp.focal_px = a.focal_px
    ball = BallDetector(bp)
    detectors = [ArucoDetector(), ball]

    if a.debug_mask:
        f = source.read()
        if f is not None:
            cv2.imwrite("ball_mask.png", ball.mask(f)[0])
            print("máscara -> ball_mask.png")

    summarize(run(source, detectors, [ConsoleSink()], a.n))


if __name__ == "__main__":
    main()
