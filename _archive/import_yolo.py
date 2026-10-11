"""[Laptop] Convierte un dataset YOLO (p. ej. Roboflow) al formato que usa
tools/calibrate_hsv.py:  <out>/<grupo>_<NNN>.jpg  +  <out>/labels.json

  python tools/import_yolo.py data/orange_pingpong --out data/ball_dataset

Decisiones (todas ajustables por flags):
  * Se FUSIONAN train/valid/test: la partición de Roboflow (19 imágenes) es
    demasiado pequeña; la validación la hace calibrate_hsv.py con CV.
  * Caja -> círculo:  cx, cy en px y r = (w + h) / 4  (promedio de semiejes).
    Si el dataset fue estirado a cuadrado, la pelota es una elipse; el
    detector tolera razones de ejes ~1.5 (ver circularidad/llenado).
  * Cajas con diámetro < --min-diam px son indetectables por diseño
    (min_radius_px del detector = 6). No se pueden etiquetar como "no pelota"
    ni como pelota, así que las IMÁGENES que las contienen se descartan
    (--keep-small para conservarlas).
  * Grupos: calibrate_hsv.py valida "dejando un grupo fuera". Aquí no hay
    nombres de fondo, así que agrupamos por ESCENA con k-means sobre miniaturas
    de color. Fotos parecidas quedan en el mismo grupo -> no hay fuga entre
    calibración y validación. El prefijo es 'esc<k>' (sin '_').
"""
import argparse
import glob
import json
import os
import shutil
import sys

import cv2
import numpy as np


def read_items(src, min_diam):
    items, dropped, small_boxes = [], [], 0
    for split in ("train", "valid", "test"):
        for lf in sorted(glob.glob(os.path.join(src, split, "labels", "*.txt"))):
            stem = os.path.splitext(os.path.basename(lf))[0]
            imgs = glob.glob(os.path.join(src, split, "images", stem + ".*"))
            if not imgs:
                continue
            img = cv2.imread(imgs[0])
            if img is None:
                continue
            H, W = img.shape[:2]
            circles, has_small = [], False
            for line in open(lf).read().splitlines():
                p = line.split()
                if len(p) < 5:
                    continue
                cx, cy, w, h = (float(v) for v in p[1:5])
                w, h = w * W, h * H
                if max(w, h) < min_diam:
                    has_small = True
                    small_boxes += 1
                    continue
                circles.append([round(cx * W, 1), round(cy * H, 1), round((w + h) / 4, 1)])
            items.append(dict(path=imgs[0], img=img, circles=circles, small=has_small))
    return items, small_boxes


def scene_groups(items, k):
    X = np.array([cv2.resize(it["img"], (16, 16), interpolation=cv2.INTER_AREA)
                  .astype(np.float32).ravel() for it in items], np.float32)
    cv2.setRNGSeed(0)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-3)
    _, lab, _ = cv2.kmeans(X, k, None, crit, 10, cv2.KMEANS_PP_CENTERS)
    return lab.ravel()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", default="data/ball_dataset")
    ap.add_argument("--groups", type=int, default=6)
    ap.add_argument("--min-diam", type=float, default=12.0)
    ap.add_argument("--keep-small", action="store_true")
    a = ap.parse_args()

    items, n_small = read_items(a.src, a.min_diam)
    if not items:
        sys.exit("No se encontraron imágenes/etiquetas YOLO.")
    kept = [it for it in items if a.keep_small or not it["small"]]
    print(f"Imágenes leídas: {len(items)} | cajas < {a.min_diam:g}px: {n_small} | "
          f"imágenes descartadas por eso: {len(items) - len(kept)} | usadas: {len(kept)}")

    lab = scene_groups(kept, min(a.groups, len(kept)))
    os.makedirs(a.out, exist_ok=True)
    labels, counter = {}, {}
    for it, g in zip(kept, lab):
        i = counter.get(g, 0)
        counter[g] = i + 1
        name = f"esc{g}_{i:03d}.jpg"
        shutil.copy(it["path"], os.path.join(a.out, name))
        labels[name] = it["circles"]
        it["name"] = name
    json.dump(labels, open(os.path.join(a.out, "labels.json"), "w"), indent=1)

    print("Grupos de escena (imágenes / pelotas):")
    for g in sorted(counter):
        nb = sum(len(v) for k, v in labels.items() if k.startswith(f"esc{g}_"))
        print(f"  esc{g}: {counter[g]:>3} / {nb}")

    # Vista previa: 6 miniaturas por grupo, para comprobar a ojo que agrupa escenas.
    rows = []
    for g in sorted(counter):
        ths = [cv2.resize(it["img"], (160, 160)) for it, gg in zip(kept, lab) if gg == g][:6]
        ths += [np.zeros((160, 160, 3), np.uint8)] * (6 - len(ths))
        row = np.hstack(ths)
        cv2.putText(row, f"esc{g}", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        rows.append(row)
    cv2.imwrite(os.path.join(a.out, "groups_preview.jpg"), np.vstack(rows))
    print(f"-> {a.out}/labels.json y groups_preview.jpg")


if __name__ == "__main__":
    main()
