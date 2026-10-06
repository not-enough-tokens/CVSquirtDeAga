"""Detector de pelota de golf naranja (Ø 42 ± 2 mm).

Estrategia (MVP clásico, sin modelos):
  1. Reducir resolución         -> costo ~ proporcional a los píxeles
  2. Segmentar color en HSV     -> H separa "qué color" de V "cuánta luz"
  3. Morfología                 -> quitar ruido, rellenar el brillo especular
  4. Validar geometría          -> circularidad, llenado, rango de radio
  5. (Opcional) distancia       -> modelo pinhole con el diámetro conocido

El fondo variable se ataca en dos frentes: saturación mínima (rechaza
madera/café/piel, que tienen matiz naranja pero poca saturación) y la
validación geométrica (rechaza manchas naranjas que no son círculos).
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from core import Detection, Frame

BALL_DIAMETER_M = 0.042


@dataclass
class BallParams:
    # OpenCV: H ∈ [0,180), S,V ∈ [0,255]. Naranja ≈ 5–22.
    hsv_lower: tuple[int, int, int] = (5, 120, 90)
    hsv_upper: tuple[int, int, int] = (22, 255, 255)
    proc_width: int = 640                   # ancho de procesamiento (px)
    min_radius_px: float = 6.0         # en la imagen ORIGINAL
    max_radius_px: float = 400.0
    min_circularity: float = 0.65      # 4πA/P², 1 = círculo perfecto
    min_fill: float = 0.60             # A / (π r²) del círculo envolvente
    max_results: int = 1
    focal_px: float | None = None      # f en px (calibración) -> distancia

    def to_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def from_json(cls, path: str) -> "BallParams":
        with open(path) as f:
            d = json.load(f)
        for k in ("hsv_lower", "hsv_upper"):
            d[k] = tuple(d[k])
        return cls(**d)

    @staticmethod
    def radius_bounds_from_distance(focal_px: float, z_min: float, z_max: float):
        """r = f·D / (2Z): convierte un rango de distancias (m) a radios (px)."""
        return (focal_px * BALL_DIAMETER_M / (2 * z_max),
                focal_px * BALL_DIAMETER_M / (2 * z_min))


class BallDetector:
    name = "ball"

    def __init__(self, params: BallParams | None = None):
        self.p = params or BallParams()
        self._k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self._k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

    def preprocess(self, img: np.ndarray) -> tuple[np.ndarray, float]:
        """BGR -> HSV reducido y suavizado. La calibración usa esta MISMA
        función: si calibras con otro preprocesamiento, los umbrales no
        describen lo que el detector realmente ve."""
        scale = min(1.0, self.p.proc_width / img.shape[1])
        if scale < 1.0:
            img = cv2.resize(img, None, fx=scale, fy=scale,
                             interpolation=cv2.INTER_AREA)
        img = cv2.GaussianBlur(img, (5, 5), 0)
        return cv2.cvtColor(img, cv2.COLOR_BGR2HSV), scale

    def mask(self, frame: Frame) -> tuple[np.ndarray, float]:
        """Máscara binaria a resolución de procesamiento + factor de escala."""
        hsv, scale = self.preprocess(frame.image)
        m = cv2.inRange(hsv, np.array(self.p.hsv_lower), np.array(self.p.hsv_upper))
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, self._k_open)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, self._k_close)
        return m, scale

    def detect(self, frame: Frame) -> list[Detection]:
        p = self.p
        m, scale = self.mask(frame)
        contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        cands = []
        for c in contours:
            area = cv2.contourArea(c)
            (x, y), r = cv2.minEnclosingCircle(c)
            r_orig = r / scale
            if not (p.min_radius_px <= r_orig <= p.max_radius_px):
                continue
            perim = cv2.arcLength(c, True)
            if perim == 0:
                continue
            circ = 4 * math.pi * area / perim ** 2
            fill = area / (math.pi * r * r)
            if circ < p.min_circularity or fill < p.min_fill:
                continue

            conf = min(1.0, circ) * min(1.0, fill)
            extra = {"circularity": round(circ, 3), "fill": round(fill, 3)}
            if p.focal_px:
                extra["distance_m"] = p.focal_px * BALL_DIAMETER_M / (2 * r_orig)
            cands.append(Detection("ball", "golf_orange",
                                   (x / scale, y / scale), r_orig, conf, extra))

        cands.sort(key=lambda d: d.confidence, reverse=True)
        return cands[: p.max_results]
