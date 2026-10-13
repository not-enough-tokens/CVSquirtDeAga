#!/data/data/com.termux/files/usr/bin/env python
"""Prueba de ida y vuelta celular -> Arduino por USB, mirando solo el LED integrado.

En el Arduino debe estar cargado el entorno `ledtest` (pio run -e ledtest -t upload).

    termux-usb -r /dev/bus/usb/001/004
    termux-usb -e ./phone/led_test.py /dev/bus/usb/001/004

(usa el numero que te de `termux-usb -l` para el Arduino; el otro es el hub.)
Mira el LED "L" de la placa mientras corre y compara con la columna "esperado".
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usb_serial import Ch340Transport  # noqa: E402

STEPS = [
    ("D,312,244,60,7", "LED ENCENDIDO fijo (hay bola)", "OK 312 244 60 7", 2.5),
    ("D,-1,-1,-1,-1", "LED APAGADO (sin bola)", "OK -1 -1 -1 -1", 2.5),
    ("D,150,294,60,-1", "LED ENCENDIDO fijo", "OK 150 294 60 -1", 2.5),
    ("hola", "sin cambio en el LED; responde ERR", "ERR", 1.5),
]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    t = Ch340Transport(int(sys.argv[1]))
    ok = 0
    buf = b""
    try:
        for line, expect, reply, wait in STEPS:
            t.write((line + "\n").encode("ascii"))
            print(f"-> {line:18s} esperado: {expect}")
            end = time.time() + wait
            got = []
            while time.time() < end:
                buf += t.read(100)
                while b"\n" in buf:
                    msg, buf = buf.split(b"\n", 1)
                    msg = msg.decode("ascii", "replace").strip()
                    if msg:
                        got.append(msg)
                        print(f"<- {msg}")
            ok += reply in got
        print(f"\nEco correcto: {ok}/{len(STEPS)}")
        print("Ahora no envio nada: en ~3 s el LED debe pasar a parpadeo lento (sin enlace).")
        time.sleep(5)
    finally:
        t.close()
    return 0 if ok == len(STEPS) else 3


if __name__ == "__main__":
    sys.exit(main())
