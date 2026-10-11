"""Calibración en sitio: un clic sobre la pelota -> umbrales HSV nuevos.

Idea: el clic da una SEMILLA en HSV. Se aceptan los píxeles dentro de una caja
alrededor de la semilla (±h_tol, ±s_tol, ±v_tol) y se toma la componente
conexa que contiene el clic: así se aísla "la pelota" sin saber su radio. Los
umbrales finales son los percentiles 2–98 de esa componente más un pequeño
margen. Es la versión rápida de tools/calibrate_hsv.py: un solo ejemplo y sin
validación, para ensayar con un objeto sustituto en el lugar de la reunión.
Limitación: no maneja matices que cruzan 0/179 (rojo); el naranja no lo hace.
"""
from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np

from detectors import BallDetector, BallParams


def params_from_click(img: np.ndarray, x: float, y: float, base: BallParams,
                      h_tol: int = 8, s_tol: int = 70, v_tol: int = 90,
                      margin=(2, 15, 20)) -> tuple[BallParams, dict]:
    """(x, y) en píxeles de la imagen ORIGINAL. Devuelve (parámetros nuevos, info)."""
    hsv, scale = BallDetector(base).preprocess(img)      # el MISMO preprocesado del detector
    hgt, wid = hsv.shape[:2]
    px = int(np.clip(round(x * scale), 0, wid - 1))
    py = int(np.clip(round(y * scale), 0, hgt - 1))

    patch = hsv[max(py - 2, 0):py + 3, max(px - 2, 0):px + 3].reshape(-1, 3)
    seed = np.median(patch, axis=0).astype(int)
    if seed[1] < 60:
        raise ValueError(f"Ahí casi no hay color (S={seed[1]}). Haz clic en la parte coloreada de la pelota.")
    if seed[0] < 3 or seed[0] > 176:
        raise ValueError("Matiz cerca de 0/179 (rojo): no soportado por esta calibración rápida.")

    tol = np.array([h_tol, s_tol, v_tol])
    lo = np.clip(seed - tol, 0, 255).astype(np.uint8)
    hi = np.clip(seed + tol, 0, [179, 255, 255]).astype(np.uint8)
    box = cv2.inRange(hsv, lo, hi)
    _, lab = cv2.connectedComponents(box)
    comp = lab == lab[py, px]
    area = int(comp.sum())
    frac = area / (hgt * wid)
    if lab[py, px] == 0 or area < 30:
        raise ValueError("Región demasiado pequeña. Acerca la pelota o haz clic más al centro.")
    if frac > 0.35:
        raise ValueError(f"La región cubre el {frac:.0%} de la imagen: el fondo se parece a la pelota. "
                         "Cambia de fondo o de iluminación.")

    v = hsv[comp]
    p_lo = np.percentile(v, 2, axis=0).astype(int)
    p_hi = np.percentile(v, 98, axis=0).astype(int)
    lower = (int(max(p_lo[0] - margin[0], 0)), int(max(p_lo[1] - margin[1], 0)),
             int(max(p_lo[2] - margin[2], 0)))
    upper = (int(min(p_hi[0] + margin[0], 179)), 255, 255)
    new = replace(base, hsv_lower=lower, hsv_upper=upper)
    info = {"seed_hsv": seed.tolist(), "area_px": area, "radio_equiv_px": round(float(np.sqrt(area / np.pi) / scale), 1),
            "hsv_lower": list(lower), "hsv_upper": list(upper)}
    return new, info
