"""Loop principal: captura -> N detectores -> sinks. Mide cada etapa.

stream() es el único bucle del proyecto: main.py lo usa a través de run() y
live.py lo consume directamente (necesita la imagen y un bucle sin fin).
"""
from __future__ import annotations

import itertools
import statistics
import time
from contextlib import nullcontext
from typing import Iterator

from core import Detector, Frame, FrameResult


class ConsoleSink:
    def send(self, r: FrameResult) -> None:
        dets = ", ".join(
            f"{d.kind}:{d.label}@({d.center[0]:.0f},{d.center[1]:.0f}) s={d.size:.1f}"
            + (f" z={d.extra['distance_m']:.2f}m" if "distance_m" in d.extra else "")
            for d in r.detections) or "-"
        t = " ".join(f"{k}={v*1e3:.1f}ms" for k, v in r.timings.items())
        print(f"[{r.frame_index:03d}] {t} | {dets}")


def stream(source, detectors: list[Detector], fail_tolerance: int = 5,
           interval: float = 0.0, lock=None) -> Iterator[tuple[Frame, FrameResult]]:
    """Generador infinito: produce (frame, resultado) por cada captura exitosa.

    fail_tolerance: capturas fallidas CONSECUTIVAS permitidas; al alcanzarla
        lanza RuntimeError (un éxito reinicia la cuenta).
    interval: pausa extra tras cada ciclo (s).
    lock: si se da, se toma durante la detección, para poder cambiar los
        parámetros de un detector desde otro hilo sin que cambien a mitad.
    """
    fails = 0
    while True:
        t0 = time.perf_counter()
        frame = source.read()
        t_cap = time.perf_counter() - t0
        if frame is None:
            fails += 1
            print(f"captura fallida ({fails}/{fail_tolerance})")
            if fails >= fail_tolerance:
                raise RuntimeError("Demasiados fallos de captura consecutivos.")
            time.sleep(1)
            continue
        fails = 0

        timings = {"capture": t_cap}
        detections = []
        with (lock or nullcontext()):
            for det in detectors:                  # secuencial: primero medir
                t0 = time.perf_counter()
                detections += det.detect(frame)
                timings[det.name] = time.perf_counter() - t0

        yield frame, FrameResult(frame.index, frame.t_capture, detections, timings)
        if interval > 0:
            time.sleep(interval)


def run(source, detectors: list[Detector], sinks: list, n: int | None = None,
        **kw) -> list[FrameResult]:
    """n ciclos exitosos (None = hasta Ctrl-C). Devuelve lo acumulado aunque se interrumpa."""
    results = []
    try:
        for _, r in itertools.islice(stream(source, detectors, **kw), n):
            for s in sinks:
                s.send(r)
            results.append(r)
    except (RuntimeError, KeyboardInterrupt) as e:
        print(f"\nInterrumpido: {e or 'Ctrl-C'}")
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
