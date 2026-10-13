"""Enlace Python -> Arduino: serializa detecciones en una línea de texto y la escribe
por un "transporte" (hoy: puerto serie con pyserial; para el teléfono habrá otro).

Protocolo v2 (ASCII, una línea por mensaje, 115200 baud):  M,<bola>,<n>,<id1>,...,<idn>\\n
  bola : 1 si se ve la pelota, 0 si no (solo depuración)
  n    : cuántos ArUco se reportan (máx. MAX_IDS)
  idk  : ids de los ArUco, el más grande (el más cercano) primero, sin repetir
  Ejemplos:  M,1,3,7,12,3   M,0,0
El mismo texto lo entiende arduino/src/main.cpp y se puede teclear a mano
en el monitor serie (pio device monitor) para probar el LCD sin Python.

Este módulo NO importa cv2/numpy: corre en una laptop con solo `pip install pyserial`.

Prueba rápida desde la laptop (Arduino por USB):
    python link.py --list                   # ver puertos (p. ej. COM5)
    python link.py --port COM5 --demo       # manda datos falsos cada segundo
"""
from __future__ import annotations

import argparse
import time
from types import SimpleNamespace
from typing import Protocol

NONE = -1


MAX_IDS = 8            # debe coincidir con MAX_IDS de arduino/src/main.cpp
MAX_ID = 999


def encode(detections) -> str:
    """Detecciones (objetos con kind, label, center, size, confidence) -> línea del protocolo v2."""
    ball = any(d.kind == "ball" for d in detections)
    ids: list[int] = []
    for d in sorted((d for d in detections if d.kind == "aruco"), key=lambda d: -d.size):
        i = int(d.label)
        if 0 <= i <= MAX_ID and i not in ids:       # sin repetidos; fuera de rango no cabe en el protocolo
            ids.append(i)
    ids = ids[:MAX_IDS]
    return "M," + ",".join(map(str, [int(ball), len(ids), *ids])) + "\n"


class Transport(Protocol):
    def write(self, data: bytes) -> None: ...
    def close(self) -> None: ...


class SerialTransport:
    """Puerto serie con pyserial (PC/laptop; en Android no hay /dev/ttyACM*)."""

    def __init__(self, port: str, baud: int = 115200, boot_wait: float = 2.0):
        import serial                       # import tardío: solo se exige si se usa
        self._s = serial.Serial(port, baud, timeout=0.1, write_timeout=1.0)
        # Abrir el puerto activa DTR y el Arduino Uno se reinicia; lo escrito antes
        # de que termine de arrancar se pierde. Se espera a que el bootloader acabe.
        time.sleep(boot_wait)

    def write(self, data: bytes) -> None:
        self._s.write(data)
        self._s.flush()

    def close(self) -> None:
        self._s.close()


def add_arguments(ap) -> None:
    """Opciones comunes de main.py / live.py."""
    g = ap.add_argument_group("Arduino (opcional)")
    g.add_argument("--arduino-fd", type=int, metavar="FD",
                   help="celular: file descriptor que entrega termux-usb (ver phone/usb_launch.sh)")
    g.add_argument("--arduino-port", metavar="PUERTO",
                   help="laptop: puerto serie con pyserial (p. ej. COM8)")


def sink_from_args(a):
    """ArduinoSink segun las opciones, o None si no se pidio. Abre el transporte."""
    if a.arduino_fd is not None:
        import os, sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "phone"))
        from usb_serial import Ch340Transport      # solo se exige en el celular
        t = Ch340Transport(a.arduino_fd)
    elif a.arduino_port:
        t = SerialTransport(a.arduino_port)
    else:
        return None
    print("[arduino] enlace abierto")
    return ArduinoSink(t, verbose=True)


class ArduinoSink:
    """Se conecta al pipeline igual que ConsoleSink: send(FrameResult)."""

    def __init__(self, transport: Transport, verbose: bool = False):
        self.t = transport
        self.verbose = verbose

    def send(self, r) -> None:
        line = encode(r.detections)
        try:
            self.t.write(line.encode("ascii"))
        except Exception as e:             # un enlace caído no debe tumbar la visión
            print(f"[arduino] no se pudo enviar: {e}")
            return
        if self.verbose:
            print(f"[arduino] {line.strip()}")

    def close(self) -> None:
        try:
            self.t.close()
        except Exception:                  # noqa: BLE001
            pass


def _demo(transport: Transport, period: float) -> None:
    """Datos falsos que recorren los casos del protocolo."""
    def ball(x, y, r, c=0.9):
        return SimpleNamespace(kind="ball", label="orange", center=(x, y), size=r, confidence=c)

    def mark(i, side):
        return SimpleNamespace(kind="aruco", label=i, center=(0, 0), size=side, confidence=1.0)

    script = [[ball(320, 240, 60), mark(7, 120)], [ball(150, 294, 25)], [mark(12, 80)], [],
              [ball(500, 100, 12), mark(3, 40), mark(9, 200)],
              [mark(i, 100 - i) for i in (41, 42, 43, 44, 45, 46)]]
    i = 0
    while True:
        line = encode(script[i % len(script)])
        transport.write(line.encode("ascii"))
        print("->", line.strip())
        i += 1
        time.sleep(period)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="lista los puertos serie")
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--period", type=float, default=1.0)
    a = ap.parse_args()

    if a.list:
        from serial.tools import list_ports
        for p in list_ports.comports():
            print(f"{p.device}\t{p.description}\tVID:PID={p.vid and format(p.vid, '04x')}:{p.pid and format(p.pid, '04x')}")
        return
    if not (a.port and a.demo):
        ap.error("usa --list, o --port <puerto> --demo")
    t = SerialTransport(a.port, a.baud)
    try:
        _demo(t, a.period)
    except KeyboardInterrupt:
        print("\nFin.")
    finally:
        t.close()

if __name__ == "__main__":
    main()
