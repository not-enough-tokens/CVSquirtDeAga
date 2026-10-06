"""Loop principal: una captura -> N detectores -> sinks. Mide cada etapa."""
from __future__ import annotations

import statistics
import time

from core import Detector, FrameResult


class ConsoleSink:
    def send(self, r: FrameResult) -> None:
        dets = ", ".join(
            f"{d.kind}:{d.label}@({d.center[0]:.0f},{d.center[1]:.0f}) s={d.size:.1f}"
            + (f" z={d.extra['distance_m']:.2f}m" if "distance_m" in d.extra else "")
            for d in r.detections) or "-"
        t = " ".join(f"{k}={v*1e3:.1f}ms" for k, v in r.timings.items())
        print(f"[{r.frame_index:03d}] {t} | {dets}")


def run(source, detectors: list[Detector], sinks: list, n: int) -> list[FrameResult]:
    results = []
    for _ in range(n):
        t0 = time.perf_counter()
        frame = source.read()
        t_cap = time.perf_counter() - t0
        if frame is None:
            continue

        timings = {"capture": t_cap}
        detections = []
        for det in detectors:                      # secuencial: primero medir
            t0 = time.perf_counter()
            detections += det.detect(frame)
            timings[det.name] = time.perf_counter() - t0

        r = FrameResult(frame.index, frame.t_capture, detections, timings)
        for s in sinks:
            s.send(r)
        results.append(r)
    return results


def summarize(results: list[FrameResult]) -> None:
    if not results:
        print("Sin ciclos exitosos.")
        return
    print(f"\nCiclos: {len(results)}")
    for k in results[0].timings:
        xs = [r.timings[k] for r in results]
        print(f"  {k:<8} mean={statistics.mean(xs)*1e3:8.1f}ms  max={max(xs)*1e3:8.1f}ms")
    totals = [sum(r.timings.values()) for r in results]
    print(f"  FPS efectivo = 1/mean(total) = {1/statistics.mean(totals):.2f}")
