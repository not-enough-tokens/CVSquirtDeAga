#!/data/data/com.termux/files/usr/bin/env python
"""Reconocimiento del Arduino por USB desde Termux (sin root). Solo LEE: no escribe nada.

Preparacion (una vez, en Termux):
    pkg install termux-api libusb python      # y la app "Termux:API" instalada desde la misma fuente que Termux
    pip install libusb1
    chmod +x phone/probe_usb.py

Uso, con el Arduino conectado al celular por USB-C -> USB-B:
    termux-usb -l                                   # lista, p. ej. ["/dev/bus/usb/001/002"]
    termux-usb -r /dev/bus/usb/001/002              # pide permiso: acepta el dialogo de Android
    termux-usb -e ./phone/probe_usb.py /dev/bus/usb/001/002

termux-usb abre el dispositivo y le pasa el file descriptor a este script como argumento
(en Android no se puede abrir /dev/bus/usb/... directamente sin root, y no hay /dev/ttyACM*).
"""
import sys

KNOWN = {
    (0x1A86, 0x7523): "CH340/CH341 (el clon tipico). Puente propietario: baudios por peticiones de vendedor.",
    (0x1A86, 0x7522): "CH340K. Igual que el CH340.",
    (0x1A86, 0x5523): "CH341 en modo serie. Igual que el CH340.",
    (0x0403, 0x6001): "FTDI FT232R. Baudios por peticiones de vendedor FTDI.",
    (0x10C4, 0xEA60): "Silicon Labs CP210x. Peticiones de vendedor propias.",
    (0x2341, 0x0043): "Arduino Uno original (ATmega16U2): CDC-ACM estandar.",
    (0x2341, 0x0001): "Arduino Uno antiguo: CDC-ACM estandar.",
    (0x2341, 0x0243): "Arduino Uno R3 (variante): CDC-ACM estandar.",
    (0x2A03, 0x0043): "Uno de dog hunter / clon con 16U2: CDC-ACM estandar.",
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    try:
        fd = int(sys.argv[1])
    except ValueError:
        print("El primer argumento debe ser el file descriptor que entrega termux-usb.")
        return 1

    try:
        import usb1
    except ImportError:
        print("Falta libusb1:  pip install libusb1   (y  pkg install libusb)")
        return 1

    # En Android no hay enumeracion normal de dispositivos; conviene desactivarla si la version lo permite.
    try:
        ctx = usb1.USBContext(with_device_discovery=False)
    except TypeError:
        ctx = usb1.USBContext()

    with ctx:
        try:
            handle = ctx.wrapSysDevice(fd)
        except Exception as e:  # noqa: BLE001
            print(f"wrapSysDevice({fd}) fallo: {type(e).__name__}: {e}")
            print("Pistas: version de libusb < 1.0.23 (pkg upgrade libusb), o el permiso no fue concedido (-r).")
            return 2

        dev = handle.getDevice()
        vid, pid = dev.getVendorID(), dev.getProductID()
        print(f"VID:PID = {vid:04x}:{pid:04x}")
        print("Chip probable:", KNOWN.get((vid, pid), "desconocido: pasame este VID:PID y las interfaces de abajo"))
        for name in ("getManufacturer", "getProduct"):
            try:
                print(f"{name[3:]}: {getattr(handle, name)()}")
            except Exception:  # noqa: BLE001
                print(f"{name[3:]}: (no disponible)")

        print("Interfaces:")
        try:
            for cfg in dev:
                for iface in cfg:
                    for st in iface:
                        eps = ", ".join(
                            f"0x{ep.getAddress():02x} attr={ep.getAttributes():#04x} max={ep.getMaxPacketSize()}"
                            for ep in st
                        )
                        print(f"  #{st.getNumber()} clase={st.getClass():#04x} sub={st.getSubClass():#04x} "
                              f"proto={st.getProtocol():#04x}  endpoints: {eps}")
        except Exception as e:  # noqa: BLE001
            print(f"  (no pude leer los descriptores: {type(e).__name__}: {e})")
        print("\nClase 0x02 = CDC (ACM estandar); 0x0a = datos CDC; 0xff = especifica del fabricante (CH340/FTDI/CP210x).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
