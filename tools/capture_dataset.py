"""[Termux] Captura un dataset de fotos para calibrar el detector.

  python tools/capture_dataset.py -n 5 --prefix madera --out dataset
  python tools/capture_dataset.py -n 5 --prefix gris   --out dataset

--prefix nombra el GRUPO (fondo / iluminación): madera_000.jpg, madera_001.jpg...
calibrate_hsv.py --cv group deja fuera un grupo completo en cada pliegue.

Entre fotos mueve la pelota: distancias, ángulos, fondos, sombras.
Incluye también 2–3 fotos SIN pelota: son los negativos que miden
cuántos falsos positivos genera el fondo.
"""
import argparse
import os
import re
import subprocess
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=15)
    ap.add_argument("--interval", type=float, default=3.0, help="segundos entre fotos")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--out", default="dataset")
    ap.add_argument("--prefix", default="img", help="grupo: fondo/condición (sin '_')")
    a = ap.parse_args()

    if "_" in a.prefix:
        raise SystemExit("--prefix no debe contener '_' (separa grupo de índice)")
    os.makedirs(a.out, exist_ok=True)
    # max índice existente + 1 (no el conteo: con huecos, el conteo sobrescribe)
    pat = re.compile(rf"^{re.escape(a.prefix)}_(\d+)\.jpg$")
    idx = [int(m.group(1)) for f in os.listdir(a.out) if (m := pat.match(f))]
    start = max(idx, default=-1) + 1

    for k in range(a.n):
        path = os.path.join(a.out, f"{a.prefix}_{start + k:03d}.jpg")
        print(f"[{k + 1}/{a.n}] capturando {path} ...", end=" ", flush=True)
        try:
            subprocess.run(["termux-camera-photo", "-c", str(a.camera), path],
                           check=True, timeout=15)
            ok = os.path.exists(path) and os.path.getsize(path) > 0
            print("ok" if ok else "archivo vacío")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                FileNotFoundError) as e:
            print(f"falló: {e}")
        if k < a.n - 1:
            time.sleep(a.interval)


if __name__ == "__main__":
    main()
