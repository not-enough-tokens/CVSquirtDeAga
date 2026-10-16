#!/data/data/com.termux/files/usr/bin/env python
"""Escribe el VID:PID del dispositivo USB cuyo fd entrega termux-usb en ~/.cv_vidpid.
Lo usa run.sh para elegir el dispositivo correcto sin depender del numero de bus."""
import os
import sys

OUT = os.path.join(os.path.expanduser("~"), ".cv_vidpid")


def main():
    fd = int(sys.argv[1])
    import usb1
    try:
        ctx = usb1.USBContext(with_device_discovery=False)
    except TypeError:
        ctx = usb1.USBContext()
    with ctx:
        dev = ctx.wrapSysDevice(fd).getDevice()
        txt = f"{dev.getVendorID():04x}:{dev.getProductID():04x}"
    with open(OUT, "w") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        with open(OUT, "w") as f:
            f.write(f"error:{type(e).__name__}\n")
