"""Calibra los umbrales HSV del BallDetector a partir de fotos etiquetadas.

  python tools/calibrate_hsv.py dataset --out ball_params.json            # CV por grupo
  python tools/calibrate_hsv.py dataset --cv loo                          # leave-one-out
  python tools/calibrate_hsv.py dataset --cv none                         # sin validación

Planteamiento
-------------
El umbral HSV es un clasificador de píxeles cuya región de aceptación es una
caja  B = [h_lo, h_hi] × [s_lo, 255] × [v_lo, 255].  Buscamos la caja que
mejor separa los píxeles de la pelota (P) de los del fondo (N).

Etapa 1 (píxeles, búsqueda exhaustiva):
  Para cada caja,  TP = |P ∩ B|,  FP = |N ∩ B|,  FN = |P| − TP,  y
  F1 = 2TP / (2TP + FP + FN).  Con ~2·10^6 cajas candidatas, contar píxeles
  imagen por imagen sería caro. En su lugar construimos histogramas 3D
  h_P, h_N y sus volúmenes integrales (sumas acumuladas en los 3 ejes):
      I[i,j,k] = Σ_{h<i, s<j, v<k} hist[h,s,v]
  y así cualquier caja se cuenta en O(1) por inclusión–exclusión (8 términos).
  Es la extensión 3D de la "summed-area table".
  Los K candidatos se eligen con supresión de no-máximos en el espacio de
  parámetros: sin ella, el top-K son K copias de la misma caja ±1 bin.

Etapa 2 (objetos):
  Un F1 de píxeles alto no garantiza detectar la pelota: la morfología y la
  validación geométrica también deciden. Los K candidatos se evalúan con el
  detector completo, y se elige por F1 de objetos (desempate: F1 de píxeles).

Validación cruzada:
  Etapas 1+2 son el "procedimiento de calibración". La CV estima qué tan bien
  generaliza ESE procedimiento: en cada pliegue calibra sin las imágenes de
  prueba y evalúa sobre ellas; TP/FP/FN se suman sobre pliegues (micro-F1).
  Los parámetros finales se calibran con TODAS las imágenes.
    --cv group : leave-one-group-out, grupo = prefijo del nombre
                 (madera_003.jpg -> "madera"). Mide generalización a un
                 fondo/condición NO visto: sin fuga entre fotos del mismo fondo.
    --cv loo   : leave-one-out por imagen.

Banda de exclusión: los píxeles entre 0.85r y 1.2r de cada etiqueta se ignoran.
Tu clic del borde tiene error de algunos píxeles; sin esta banda, ese error
entraría a las estadísticas como "fondo naranja" o "pelota no naranja".
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import OrderedDict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import cv2  # noqa: E402

from core import Frame  # noqa: E402
from detectors import BallDetector, BallParams  # noqa: E402

SB = VB = 64                 # bins de S y V (ancho 4); H usa sus 180 valores
SHAPE = (180, SB, VB)


def group_of(name: str) -> str:
    stem = os.path.splitext(name)[0]
    return stem.rsplit("_", 1)[0] if "_" in stem else stem


# ---------------------------------------------------------------- datos
def load(dataset, labels_path, proc_width, inner, outer):
    """Por imagen: (nombre, img, círculos, hist_pos, hist_neg, px_pelota).
    Los histogramas se calculan UNA vez; cada pliegue solo los suma."""
    labels = json.load(open(labels_path))
    pre = BallDetector(BallParams(proc_width=proc_width))
    data = []
    for name, circles in sorted(labels.items()):
        img = cv2.imread(os.path.join(dataset, name))
        if img is None:
            print(f"  (omitida, no se pudo leer) {name}")
            continue
        hsv, scale = pre.preprocess(img)
        hgt, wid = hsv.shape[:2]
        yy, xx = np.mgrid[:hgt, :wid]
        pos = np.zeros((hgt, wid), bool)
        near = np.zeros((hgt, wid), bool)
        for cx, cy, r in circles:
            d = np.hypot(xx - cx * scale, yy - cy * scale)
            pos |= d < inner * r * scale
            near |= d <= outer * r * scale
        idx = (hsv[..., 0].astype(np.int64) * SB + hsv[..., 1] // 4) * VB + hsv[..., 2] // 4
        n = 180 * SB * VB
        hp = np.bincount(idx[pos], minlength=n).astype(np.int32)
        hn = np.bincount(idx[~near], minlength=n).astype(np.int32)
        data.append(dict(name=name, img=img, circles=circles, hp=hp, hn=hn, px=hsv[pos]))
    return data


# ---------------------------------------------------------------- etapa 1
def integral(h):
    I = np.zeros((h.shape[0] + 1, h.shape[1] + 1, h.shape[2] + 1), np.int64)
    I[1:, 1:, 1:] = h.cumsum(0).cumsum(1).cumsum(2)
    return I


def box(I, a, b, c, d):
    """Σ hist sobre h∈[a,b], s_bin∈[c,SB), v_bin∈[d,VB). Vectorizado."""
    A, B = a, b + 1
    return (I[B, SB, VB] - I[A, SB, VB] - I[B, c, VB] + I[A, c, VB]
            - I[B, SB, d] + I[A, SB, d] + I[B, c, d] - I[A, c, d])


def search_pixels(hp, hn, h_lo_max, h_hi_max, topk, nms=2):
    Ip, In = integral(hp), integral(hn)
    P = int(hp.sum())
    pairs = np.array([(a, b) for a in range(h_lo_max + 1)
                      for b in range(a + 3, h_hi_max + 1)])
    a = pairs[:, 0][:, None, None]
    b = pairs[:, 1][:, None, None]
    c = np.arange(SB)[None, :, None]
    d = np.arange(VB)[None, None, :]
    a, b, c, d = np.broadcast_arrays(a, b, c, d)
    tp = box(Ip, a, b, c, d)
    fp = box(In, a, b, c, d)
    f1 = 2 * tp / np.maximum(2 * tp + fp + (P - tp), 1)

    # NMS: descarta candidatos a distancia L∞ ≤ nms (en bins) de uno ya elegido
    order = np.argsort(f1, axis=None)[::-1]
    out, keys = [], []
    for f in order[:200_000]:
        k = np.unravel_index(f, f1.shape)
        key = np.array([a[k], b[k], c[k], d[k]])
        if any(np.abs(key - q).max() <= nms for q in keys):
            continue
        keys.append(key)
        out.append(dict(h_lo=int(a[k]), h_hi=int(b[k]), s_lo=int(c[k]) * 4, v_lo=int(d[k]) * 4,
                        f1_pix=float(f1[k]), tp=int(tp[k]), fp=int(fp[k]), P=P))
        if len(out) == topk:
            break
    return out


# ---------------------------------------------------------------- etapa 2
def evaluate_objects(data, params: BallParams):
    det = BallDetector(params)
    TP = FP = FN = 0
    per_image = []
    for x in data:
        found = det.detect(Frame(x["img"], 0.0, 0))
        unmatched = list(x["circles"])
        tp = fp = 0
        for dd in found:
            j = next((j for j, (cx, cy, r) in enumerate(unmatched)
                      if math.hypot(dd.center[0] - cx, dd.center[1] - cy) < 0.5 * r), None)
            if j is None:
                fp += 1
            else:
                tp += 1
                unmatched.pop(j)
        TP, FP, FN = TP + tp, FP + fp, FN + len(unmatched)
        per_image.append((x["name"], tp, fp, len(unmatched)))
    return f1_of(TP, FP, FN), (TP, FP, FN), per_image


def f1_of(TP, FP, FN):
    return 2 * TP / max(2 * TP + FP + FN, 1)


# ---------------------------------------------------------------- procedimiento
def calibrate(train, a):
    """Etapas 1+2 sobre `train`. Esto es lo que la CV evalúa."""
    hp = sum(x["hp"].astype(np.int64) for x in train).reshape(SHAPE)
    hn = sum(x["hn"].astype(np.int64) for x in train).reshape(SHAPE)
    cands = search_pixels(hp, hn, a.h_lo_max, a.h_hi_max, a.topk)
    best = None
    for c in cands:
        p = BallParams(hsv_lower=(c["h_lo"], c["s_lo"], c["v_lo"]),
                       hsv_upper=(c["h_hi"], 255, 255), proc_width=a.proc_width,
                       max_results=a.max_results)
        f1o, counts, per = evaluate_objects(train, p)
        key = (f1o, c["f1_pix"])
        if best is None or key > best[0]:
            best = (key, p, c, counts, per)
    (f1o, _), p, c, counts, per = best
    return p, dict(f1_obj=f1o, counts=counts, per=per, cand=c)


def folds(data, mode):
    if mode == "loo":
        keys = [x["name"] for x in data]
        key_of = lambda x: x["name"]          # noqa: E731
    else:
        keys = list(OrderedDict.fromkeys(group_of(x["name"]) for x in data))
        key_of = lambda x: group_of(x["name"])  # noqa: E731
    for k in keys:
        yield k, [x for x in data if key_of(x) != k], [x for x in data if key_of(x) == k]


def cross_validate(data, a):
    TP = FP = FN = 0
    print(f"\nValidación cruzada ({a.cv}):")
    print(f"  {'pliegue':<16} {'n':>3}  {'hsv_lower':<16} {'TP':>3} {'FP':>3} {'FN':>3}")
    for key, train, test in folds(data, a.cv):
        if not any(x["circles"] for x in train):
            print(f"  {key:<16} omitido: sin pelotas para calibrar")
            continue
        p, _ = calibrate(train, a)
        _, (tp, fp, fn), per = evaluate_objects(test, p)
        TP, FP, FN = TP + tp, FP + fp, FN + fn
        print(f"  {key:<16} {len(test):>3}  {str(p.hsv_lower):<16} {tp:>3} {fp:>3} {fn:>3}")
    f1 = f1_of(TP, FP, FN)
    print(f"  => F1 de objetos (fuera de muestra) = {f1:.3f}   TP={TP} FP={FP} FN={FN}")
    return f1


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--labels", default=None)
    ap.add_argument("--out", default="ball_params.json")
    ap.add_argument("--cv", choices=["group", "loo", "none"], default="group")
    ap.add_argument("--proc-width", type=int, default=640)
    ap.add_argument("--max-results", type=int, default=1,
                    help="detecciones máx. por imagen al evaluar (>1 si hay varias pelotas por foto)")
    ap.add_argument("--inner", type=float, default=0.85)
    ap.add_argument("--outer", type=float, default=1.2)
    ap.add_argument("--h-lo-max", type=int, default=15)
    ap.add_argument("--h-hi-max", type=int, default=40)
    ap.add_argument("--topk", type=int, default=25)
    a = ap.parse_args()

    data = load(a.dataset, a.labels or os.path.join(a.dataset, "labels.json"),
                a.proc_width, a.inner, a.outer)
    n_pos = sum(bool(x["circles"]) for x in data)
    groups = OrderedDict.fromkeys(group_of(x["name"]) for x in data)
    print(f"Imágenes: {len(data)}  (con pelota: {n_pos}, negativas: {len(data) - n_pos})"
          f"  grupos: {list(groups)}")
    if n_pos == 0:
        sys.exit("No hay pelotas etiquetadas.")
    if a.cv == "group" and len(groups) < 2:
        sys.exit("--cv group necesita ≥ 2 grupos (prefijos de nombre). "
                 "Usa capture_dataset.py --prefix <fondo>, o --cv loo.")

    px = np.concatenate([x["px"] for x in data if len(x["px"])])
    q = [1, 5, 50, 95, 99]
    print("\nPíxeles de pelota — percentiles", q)
    for i, ch in enumerate("HSV"):
        print(f"  {ch}: {np.percentile(px[:, i], q).round(0).astype(int).tolist()}")

    cv_f1 = cross_validate(data, a) if a.cv != "none" else None

    p, info = calibrate(data, a)
    c, (TP, FP, FN) = info["cand"], info["counts"]
    print("\nCalibración final (todas las imágenes):")
    print(f"  hsv_lower={p.hsv_lower}  hsv_upper={p.hsv_upper}")
    print(f"  píxeles: F1={c['f1_pix']:.4f}  recall={c['tp']/c['P']:.3f}  FP={c['fp']}")
    print(f"  objetos (dentro de muestra, optimista): F1={info['f1_obj']:.3f}"
          f"  TP={TP} FP={FP} FN={FN}")
    if cv_f1 is not None:
        print(f"  objetos (validación cruzada, estimación honesta): F1={cv_f1:.3f}")
    bad = [x for x in info["per"] if x[2] or x[3]]
    if bad:
        print("  Fallos por imagen (nombre, tp, fp, fn):")
        for x in bad:
            print("   ", x)
    p.to_json(a.out)
    print(f"\nParámetros guardados en {a.out}")


if __name__ == "__main__":
    main()
