"""Dibujo de depuración compartido por tools/replay.py y live.py.

annotate() recibe la imagen BGR original y las Detection en sus coordenadas
(px de la imagen original) y devuelve una COPIA con cajas, etiquetas y una
franja de tiempos. No toca la imagen de entrada.
"""
from __future__ import annotations

import cv2
import numpy as np

from core import Detection

# BGR
GREEN = (60, 200, 60)
RED = (60, 60, 235)
BLUE = (235, 140, 40)
YELLOW = (0, 215, 255)
MAGENTA = (220, 60, 220)
WHITE = (255, 255, 255)


def _s(img: np.ndarray) -> float:
    """Factor de escala de textos/trazos según el ancho de la imagen."""
    return max(1.0, img.shape[1] / 800.0)


def put_text(img, text, org, color=WHITE, scale=0.6):
    s = _s(img)
    th = max(1, int(round(1.5 * s)))
    x = max(2, int(org[0]))
    y = max(int(18 * s), int(org[1]))
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale * s, (0, 0, 0), th + 2, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale * s, color, th, cv2.LINE_AA)


def draw_detection(img, d: Detection, color=None, label=True) -> None:
    s = _s(img)
    th = max(2, int(round(2 * s)))
    if d.kind == "ball":
        c = color or GREEN
        cx, cy = int(round(d.center[0])), int(round(d.center[1]))
        r = max(2, int(round(d.size)))
        cv2.circle(img, (cx, cy), r, c, th, cv2.LINE_AA)
        cv2.drawMarker(img, (cx, cy), c, cv2.MARKER_CROSS, int(12 * s), th)
        if label:
            txt = f"{d.confidence:.2f}"
            if "distance_m" in d.extra:
                txt += f"  {d.extra['distance_m']:.2f} m"
            put_text(img, txt, (cx + r + 4, cy - r), c)
    elif d.kind == "aruco":
        c = color or MAGENTA
        corners = d.extra.get("corners")
        if corners:
            pts = np.array(corners, np.int32).reshape(-1, 1, 2)
            cv2.polylines(img, [pts], True, c, th, cv2.LINE_AA)
            org = (int(pts[0, 0, 0]), int(pts[0, 0, 1]) - 6)
        else:
            h = d.size / 2
            x0, y0 = int(d.center[0] - h), int(d.center[1] - h)
            cv2.rectangle(img, (x0, y0), (int(d.center[0] + h), int(d.center[1] + h)), c, th)
            org = (x0, y0 - 6)
        if label:
            put_text(img, f"id {d.label}", org, c, 0.7)


def draw_hud(img, lines: list[str]) -> None:
    s = _s(img)
    lh = int(26 * s)
    bar = img.copy()
    cv2.rectangle(bar, (0, 0), (img.shape[1], lh * len(lines) + int(8 * s)), (0, 0, 0), -1)
    cv2.addWeighted(bar, 0.55, img, 0.45, 0, img)
    for i, t in enumerate(lines):
        put_text(img, t, (8, int(20 * s) + i * lh), WHITE)


def draw_mask_inset(img, mask: np.ndarray) -> None:
    """Miniatura de la máscara HSV (naranja sobre negro) abajo a la izquierda."""
    H, W = img.shape[:2]
    w = W // 4
    h = max(1, int(w * H / W))
    m = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    vis = np.zeros((h, w, 3), np.uint8)
    vis[m > 0] = (0, 140, 255)
    cv2.rectangle(vis, (0, 0), (w - 1, h - 1), WHITE, 1)
    img[H - h - 6:H - 6, 6:6 + w] = vis


def annotate(image: np.ndarray, detections: list[Detection],
             timings: dict[str, float] | None = None,
             mask: np.ndarray | None = None, title: str | None = None) -> np.ndarray:
    out = image.copy()
    for d in detections:
        draw_detection(out, d)
    lines = [title] if title else []
    if timings:
        parts = "  ".join(f"{k} {v * 1e3:.0f} ms" for k, v in timings.items())
        lines.append(f"{parts}  |  total {sum(timings.values()) * 1e3:.0f} ms")
    nb = sum(d.kind == "ball" for d in detections)
    na = sum(d.kind == "aruco" for d in detections)
    lines.append(f"pelotas: {nb}   aruco: {na}")
    draw_hud(out, lines)
    if mask is not None:
        draw_mask_inset(out, mask)
    return out
