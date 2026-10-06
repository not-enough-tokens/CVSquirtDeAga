"""[Laptop, requiere GUI] Etiqueta la pelota en cada foto -> labels.json

  python tools/label_balls.py dataset

Controles:
  clic 1 = centro, clic 2 = un punto del borde  -> agrega un círculo
  espacio/enter = guardar y siguiente     n = "sin pelota" y siguiente
  u = deshacer último círculo             b = imagen anterior
  q = guardar y salir

Formato: {"img_000.jpg": [[cx, cy, r], ...], ...} en píxeles de la imagen
ORIGINAL. Una lista vacía es un negativo explícito (≠ no etiquetada).
"""
import argparse
import json
import math
import os

import cv2

MAX_W = 1280


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--labels", default=None, help="por defecto <dataset>/labels.json")
    ap.add_argument("--all", action="store_true", help="revisar también las ya etiquetadas")
    a = ap.parse_args()

    lpath = a.labels or os.path.join(a.dataset, "labels.json")
    labels = json.load(open(lpath)) if os.path.exists(lpath) else {}
    files = sorted(f for f in os.listdir(a.dataset) if f.lower().endswith((".jpg", ".png")))
    todo = files if a.all else [f for f in files if f not in labels]
    if not todo:
        print("Todo etiquetado. Usa --all para revisar.")
        return

    def save():
        with open(lpath, "w") as f:
            json.dump(labels, f, indent=1)

    state = {"pending": None, "circles": []}

    def on_mouse(ev, x, y, *_):
        if ev != cv2.EVENT_LBUTTONDOWN:
            return
        if state["pending"] is None:
            state["pending"] = (x, y)
        else:
            cx, cy = state["pending"]
            state["circles"].append((cx, cy, math.hypot(x - cx, y - cy)))
            state["pending"] = None

    cv2.namedWindow("label")
    cv2.setMouseCallback("label", on_mouse)
    i = 0
    while 0 <= i < len(todo):
        name = todo[i]
        img = cv2.imread(os.path.join(a.dataset, name))
        if img is None:
            i += 1
            continue
        s = min(1.0, MAX_W / img.shape[1])
        disp = cv2.resize(img, None, fx=s, fy=s)
        state["circles"] = [(cx * s, cy * s, r * s) for cx, cy, r in labels.get(name, [])]
        state["pending"] = None

        while True:
            view = disp.copy()
            for cx, cy, r in state["circles"]:
                cv2.circle(view, (int(cx), int(cy)), int(r), (0, 255, 0), 2)
                cv2.drawMarker(view, (int(cx), int(cy)), (0, 255, 0), cv2.MARKER_CROSS, 12)
            if state["pending"]:
                cv2.drawMarker(view, state["pending"], (0, 0, 255), cv2.MARKER_CROSS, 16, 2)
            cv2.putText(view, f"{i + 1}/{len(todo)} {name}  circulos={len(state['circles'])}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow("label", view)
            k = cv2.waitKey(30) & 0xFF
            if cv2.getWindowProperty("label", cv2.WND_PROP_VISIBLE) < 1:   # cerrada con X
                save(); cv2.destroyAllWindows(); return
            if k in (13, 32):                      # enter / espacio
                labels[name] = [[round(cx / s, 1), round(cy / s, 1), round(r / s, 1)]
                                for cx, cy, r in state["circles"]]
                save(); i += 1; break
            if k == ord("n"):
                labels[name] = []
                save(); i += 1; break
            if k == ord("u") and state["circles"]:
                state["circles"].pop()
            if k == ord("b"):
                i = max(0, i - 1); break
            if k == ord("q"):
                save(); cv2.destroyAllWindows(); return
    cv2.destroyAllWindows()
    print(f"Etiquetas guardadas en {lpath}")


if __name__ == "__main__":
    main()
