"""Repite el BallDetector sobre un dataset etiquetado y genera una galería HTML.

  python debug/replay.py                                  # data/ball_dataset + ball_params.json
  python debug/replay.py --params data/ball_params_pingpong.json --serve

Por imagen se dibuja:
  azul fino   = pelota etiquetada y encontrada
  amarillo    = pelota etiquetada NO encontrada  (FN)
  verde       = detección correcta               (TP)
  rojo        = detección sin pelota etiquetada  (FP)
La página pone primero las imágenes con errores. --serve la sirve en
127.0.0.1:8000 (acceso por túnel SSH si corres esto en el teléfono).

Ojo: si los parámetros se calibraron con ESTAS mismas imágenes, la cifra es
optimista (dentro de muestra); la estimación honesta es la de calibrate_hsv.py --cv.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import cv2  # noqa: E402

from core import Frame  # noqa: E402
from detectors import BallDetector, BallParams  # noqa: E402
from debug.viz import BLUE, GREEN, RED, YELLOW, annotate, draw_detection, put_text  # noqa: E402
from core import Detection  # noqa: E402

BINS = ((0, 10, "r < 10 px"), (10, 25, "10–25 px"), (25, 60, "25–60 px"), (60, 1e9, "r ≥ 60 px"))


def match(dets, circles):
    """Igual que calibrate_hsv.evaluate_objects: centro a < 0.5 r de la etiqueta."""
    un = list(circles)
    tp, fp = [], []
    for d in dets:
        j = next((j for j, (cx, cy, r) in enumerate(un)
                  if math.hypot(d.center[0] - cx, d.center[1] - cy) < 0.5 * r), None)
        if j is None:
            fp.append(d)
        else:
            tp.append((d, un.pop(j)))
    return tp, fp, un          # un = FN


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", nargs="?", default="data/ball_dataset")
    ap.add_argument("--params", default="ball_params.json")
    ap.add_argument("--max-balls", type=int, default=10)
    ap.add_argument("--out", default="out/replay")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()

    labels = json.load(open(os.path.join(a.dataset, "labels.json")))
    bp = BallParams.from_json(a.params) if os.path.exists(a.params) else BallParams()
    bp.max_results = a.max_balls
    det = BallDetector(bp)
    os.makedirs(a.out, exist_ok=True)

    TP = FP = FN = 0
    by_bin = {b[2]: [0, 0] for b in BINS}            # [encontradas, total]
    cards = []
    for name, circles in sorted(labels.items()):
        img = cv2.imread(os.path.join(a.dataset, name))
        if img is None:
            continue
        dets = det.detect(Frame(img, time.perf_counter(), 0))
        tp, fp, fn = match(dets, circles)
        TP, FP, FN = TP + len(tp), FP + len(fp), FN + len(fn)
        for (cx, cy, r) in circles:
            b = next(x[2] for x in BINS if x[0] <= r < x[1])
            by_bin[b][1] += 1
        for _, (cx, cy, r) in tp:
            by_bin[next(x[2] for x in BINS if x[0] <= r < x[1])][0] += 1

        vis = img.copy()
        for _, (cx, cy, r) in tp:
            cv2.circle(vis, (int(cx), int(cy)), int(r), BLUE, 1, cv2.LINE_AA)
        for (cx, cy, r) in fn:
            cv2.circle(vis, (int(cx), int(cy)), int(r), YELLOW, 3, cv2.LINE_AA)
        for d, _ in tp:
            draw_detection(vis, d, GREEN, label=False)
        for d in fp:
            draw_detection(vis, d, RED, label=False)
        put_text(vis, f"{name}  TP {len(tp)}  FP {len(fp)}  FN {len(fn)}", (6, 20))
        cv2.imwrite(os.path.join(a.out, name), vis, [cv2.IMWRITE_JPEG_QUALITY, 85])
        cards.append((name, len(tp), len(fp), len(fn)))

    prec = TP / max(TP + FP, 1)
    rec = TP / max(TP + FN, 1)
    f1 = 2 * TP / max(2 * TP + FP + FN, 1)
    bad = [c for c in cards if c[2] or c[3]]
    good = [c for c in cards if not (c[2] or c[3])]

    def grid(items):
        return "".join(
            f'<figure class="{"bad" if (c[2] or c[3]) else "ok"}"><img loading="lazy" '
            f'src="{html.escape(c[0])}"><figcaption>{html.escape(c[0])}: '
            f'TP {c[1]} · FP {c[2]} · FN {c[3]}</figcaption></figure>' for c in items)

    rows = "".join(f"<tr><td>{k}</td><td>{v[1]}</td><td>{v[0] / v[1]:.2f}</td></tr>"
                   for k, v in by_bin.items() if v[1])
    page = f"""<!doctype html><meta charset="utf-8"><title>Repetición BallDetector</title>
<style>
body{{background:#14161a;color:#e8e8e8;font:15px system-ui;margin:0;padding:16px 24px}}
h1{{font-size:20px}} h2{{font-size:16px;margin-top:28px}}
.stats span{{display:inline-block;margin-right:22px}} b{{font-size:22px}}
table{{border-collapse:collapse;margin:8px 0}} td,th{{padding:3px 14px;border-bottom:1px solid #333}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}}
figure{{margin:0;background:#1e2127;padding:6px;border-radius:6px}} figure img{{width:100%;display:block}}
figcaption{{font-size:12px;color:#aaa;padding-top:4px}} .bad{{outline:2px solid #e0a000}}
.leg i{{display:inline-block;width:12px;height:12px;border-radius:50%;margin:0 4px 0 14px;vertical-align:-1px}}
.note{{color:#9aa;max-width:820px}}
</style>
<h1>BallDetector sobre {len(cards)} imágenes etiquetadas</h1>
<div class="stats"><span>precisión <b>{prec:.3f}</b></span><span>recall <b>{rec:.3f}</b></span>
<span>F1 <b>{f1:.3f}</b></span><span>TP {TP} · FP {FP} · FN {FN}</span></div>
<p class="leg"><i style="background:#2a8cea"></i>etiqueta encontrada<i style="background:#ffd700"></i>etiqueta NO encontrada (FN)
<i style="background:#3cc83c"></i>detección correcta<i style="background:#eb3c3c"></i>falso positivo</p>
<p class="note">Parámetros: <code>{html.escape(a.params)}</code> — H {bp.hsv_lower[0]}–{bp.hsv_upper[0]},
S ≥ {bp.hsv_lower[1]}, V ≥ {bp.hsv_lower[2]}. Si se calibraron con estas mismas imágenes, la cifra es
optimista (dentro de muestra); la estimación honesta es la validación cruzada por escena.</p>
<table><tr><th>tamaño (radio)</th><th>pelotas</th><th>recall</th></tr>{rows}</table>
<h2>Con errores ({len(bad)})</h2><div class="grid">{grid(bad)}</div>
<h2>Sin errores ({len(good)})</h2><div class="grid">{grid(good)}</div>
"""
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"{len(cards)} imágenes | TP={TP} FP={FP} FN={FN} | precisión={prec:.3f} "
          f"recall={rec:.3f} F1={f1:.3f}")
    print(f"con errores: {len(bad)}  -> {a.out}/index.html")

    if a.serve:
        from debug.web import start_server
        start_server(a.out, "127.0.0.1", a.port)
        print(f"Sirviendo en http://127.0.0.1:{a.port}/  (Ctrl-C para salir)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
