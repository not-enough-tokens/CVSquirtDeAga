import os
import statistics
import subprocess
import time

import cv2

PHOTO_PATH = "capture.jpg"
ITERATIONS_N = 30
CAPTURE_TIMEOUT_S = 15
error_record = 0
ERROR_TOLERANCE = 5

aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
detector = cv2.aruco.ArucoDetector(aruco_dict, cv2.aruco.DetectorParameters())

cycles = []  # (t_cap, t_read, t_det, ids)

for i in range(ITERATIONS_N):
    # Borrar la foto previa: si la captura "tiene éxito" sin escribir, imread verá None
    if os.path.exists(PHOTO_PATH):
        os.remove(PHOTO_PATH)

    # --- TODO 1: captura ---
    try:
        t0 = time.perf_counter()
        subprocess.run(["termux-camera-photo", "-c", "0", PHOTO_PATH], check=True, timeout=CAPTURE_TIMEOUT_S)
        t_cap = time.perf_counter() - t0
        error_record = 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[{i:02d}] captura falló: {e}")
        error_record += 1

        if error_record >= ERROR_TOLERANCE: break

        continue

    # --- TODO 2: lectura + detección (medidas por separado) ---
    t0 = time.perf_counter()
    img = cv2.imread(PHOTO_PATH)
    t_read = time.perf_counter() - t0
    if img is None:
        print(f"[{i:02d}] imread devolvió None")

        error_record += 1

        if error_record >= ERROR_TOLERANCE: break

        continue

    t0 = time.perf_counter()
    corners, ids, _ = detector.detectMarkers(img)
    t_det = time.perf_counter() - t0

    found = [] if ids is None else ids.flatten().tolist()
    print(f"[{i:02d}] cap={t_cap:.3f}s read={t_read * 1e3:.1f}ms "
          f"det={t_det * 1e3:.1f}ms ids={found or '-'}")
    cycles.append((t_cap, t_read, t_det, found))

# --- TODO 3: estadísticas ---
if not cycles:
    raise SystemExit("Ningún ciclo exitoso.")

caps = [c[0] for c in cycles]
reads = [c[1] for c in cycles]
dets = [c[2] for c in cycles]
totals = [c + r + d for c, r, d in zip(caps, reads, dets)]


def report(name, xs, unit=1.0, suffix="s"):
    print(f"{name:<10} mean={statistics.mean(xs)*unit:8.3f}{suffix} "
          f"max={max(xs)*unit:8.3f}{suffix}")


print(f"\nCiclos exitosos: {len(cycles)}/{ITERATIONS_N}")
report("captura", caps)
report("lectura", reads, 1e3, "ms")
report("deteccion", dets, 1e3, "ms")
report("total", totals)

# FPS "real" = frames / tiempo total = 1 / mean(total)
print(f"FPS efectivo (1/mean):  {1 / statistics.mean(totals):.3f}")
# Para contraste: mean(1/total) >= 1/mean(total) por Jensen (1/x convexa)
print(f"mean(1/total) (sesgado): {statistics.mean(1 / t for t in totals):.3f}")

hit_rate = sum(bool(c[3]) for c in cycles) / len(cycles)
print(f"Tasa de detección: {hit_rate:.0%}")