"""Puerto serie para un puente CH340/CH341 sobre libusb1, para Termux (sin root).

Por que existe: en Android no hay /dev/ttyUSB* ni /dev/ttyACM*, asi que pyserial no sirve.
`termux-usb` entrega un file descriptor ya abierto y libusb habla directo con el chip.
El CH340 NO es CDC estandar: los baudios y la linea se configuran con peticiones de vendedor.
La secuencia sigue la del controlador ch341 de Linux (comprobada por el LED, ver led_test.py).

Implementa la interfaz Transport de link.py: write(bytes), close(); y ademas read().
Se usa dentro de `termux-usb -e <script> <dispositivo>`, que pasa el fd como argv[1].
"""
from __future__ import annotations

import time

EP_OUT = 0x02          # bulk OUT (visto con probe_usb.py)
EP_IN = 0x82           # bulk IN
REQ_READ_VERSION = 0x5F
REQ_WRITE_REG = 0x9A
REQ_READ_REG = 0x95
REQ_SERIAL_INIT = 0xA1
REQ_MODEM_CTRL = 0xA4
BIT_DTR = 1 << 5
BIT_RTS = 1 << 6
LCR_8N1 = 0xC3         # RX on | TX on | 8 bits, sin paridad, 1 stop
BAUDBASE_FACTOR = 1532620800
TIMEOUT_MS = 1000


def baud_registers(baud: int) -> tuple[int, int]:
    """(a, b) para las peticiones 0x9A 0x1312 y 0x9A 0x0F2C. 115200 -> (0xCC83, 0x08)."""
    factor = BAUDBASE_FACTOR // baud
    div = 3
    while factor > 0xFFF0 and div:
        factor >>= 3
        div -= 1
    if factor > 0xFFF0:
        raise ValueError(f"baudios no soportados: {baud}")
    factor = 0x10000 - factor
    a = (factor & 0xFF00) | div | 0x80      # bit 7: entregar datos sin esperar paquetes de 32 B
    b = factor & 0xFF
    return a, b


def configure(handle, baud: int = 115200, dtr: bool = False, rts: bool = False) -> None:
    """Inicializa el CH340 (8N1). `handle` necesita controlRead/controlWrite estilo libusb1."""
    def out(req, value, index):
        handle.controlWrite(0x40, req, value & 0xFFFF, index & 0xFFFF, b"", TIMEOUT_MS)

    def inn(req, value, index):
        try:
            return bytes(handle.controlRead(0xC0, req, value, index, 8, TIMEOUT_MS))
        except Exception:                   # lecturas informativas: no son fatales
            return b""

    def set_baud():
        a, b = baud_registers(baud)
        out(REQ_WRITE_REG, 0x1312, a)
        out(REQ_WRITE_REG, 0x0F2C, b)

    inn(REQ_READ_VERSION, 0, 0)
    out(REQ_SERIAL_INIT, 0, 0)
    set_baud()
    inn(REQ_READ_REG, 0x2518, 0)
    out(REQ_WRITE_REG, 0x2518, 0x0050)
    inn(REQ_READ_REG, 0x0706, 0)
    out(REQ_SERIAL_INIT, 0x501F, 0xD90A)
    set_baud()
    out(REQ_WRITE_REG, 0x2518, LCR_8N1)
    control = (BIT_DTR if dtr else 0) | (BIT_RTS if rts else 0)
    out(REQ_MODEM_CTRL, ~control, 0)        # lineas activas en bajo: ~0 = ambas inactivas


class Ch340Transport:
    """dtr=False (por defecto) NO reinicia el Arduino al abrir; con dtr=True lo reinicia
    (como hace el IDE) y entonces hay que esperar ~2 s a que acabe el bootloader."""

    def __init__(self, fd: int, baud: int = 115200, dtr: bool = False, boot_wait: float | None = None):
        import usb1                         # import tardio: solo se exige en el celular
        try:
            self._ctx = usb1.USBContext(with_device_discovery=False)
        except TypeError:
            self._ctx = usb1.USBContext()
        self._ctx.open()
        self._h = self._ctx.wrapSysDevice(fd)
        try:
            self._h.setAutoDetachKernelDriver(True)
        except Exception:                   # noqa: BLE001  (no siempre soportado en Android)
            pass
        self._h.claimInterface(0)
        configure(self._h, baud, dtr=dtr)
        time.sleep(boot_wait if boot_wait is not None else (2.0 if dtr else 0.3))

    def write(self, data: bytes) -> None:
        for i in range(0, len(data), 32):
            self._h.bulkWrite(EP_OUT, data[i:i + 32], TIMEOUT_MS)

    def read(self, timeout_ms: int = 100) -> bytes:
        """Bytes disponibles (puede ser b'' si no llego nada en timeout_ms)."""
        import usb1
        try:
            return bytes(self._h.bulkRead(EP_IN, 64, timeout_ms))
        except usb1.USBErrorTimeout as e:
            return bytes(getattr(e, "received", b"") or b"")

    def close(self) -> None:
        for fn in (lambda: self._h.releaseInterface(0), self._h.close, self._ctx.close):
            try:
                fn()
            except Exception:               # noqa: BLE001
                pass
