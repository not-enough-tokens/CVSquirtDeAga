#!/data/data/com.termux/files/usr/bin/bash
# Lanzador unico: funciona desde cualquier carpeta, aunque se haya perdido el bit de ejecucion
# o haya cambiado el numero de dispositivo USB.
#   bash ~/CVSquirtDeAga/phone/run.sh          # supervisado: si la vision termina, vuelve a buscar el Arduino y arranca
#   bash ~/CVSquirtDeAga/phone/run.sh --once   # una sola vez (depuracion)
# Ctrl-C lo detiene. Mientras corre mantiene un wake-lock (la CPU no se duerme con la pantalla apagada).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 1
cd "$ROOT" || exit 1
chmod +x phone/*.sh phone/*.py 2>/dev/null
MARK="$HOME/.cv_vidpid"
WANT="${CV_VIDPID:-1a86:7523}"
ONCE=0; [ "$1" = "--once" ] && ONCE=1
STOP=0

find_device() {          # imprime la ruta del Arduino, o nada
  local d
  for d in $(termux-usb -l | grep -o '/dev/bus/usb/[0-9]*/[0-9]*'); do
    termux-usb -r "$d" >/dev/null 2>&1
    rm -f "$MARK"
    termux-usb -e ./phone/find_arduino.py "$d" >/dev/null 2>&1
    for _ in 1 2 3 4 5 6; do [ -s "$MARK" ] && break; sleep 0.5; done
    if [ "$(cat "$MARK" 2>/dev/null)" = "$WANT" ]; then echo "$d"; return 0; fi
  done
  return 1
}

command -v termux-wake-lock >/dev/null && termux-wake-lock
trap 'termux-wake-unlock 2>/dev/null' EXIT
trap 'STOP=1' INT TERM

while [ "$STOP" -eq 0 ]; do
  DEV="$(find_device)"
  if [ -z "$DEV" ]; then
    echo "[run] no hay dispositivo $WANT (termux-usb -l ve: $(termux-usb -l | tr -d '\n '))"
    [ "$ONCE" -eq 1 ] && exit 1
    sleep 3; continue
  fi
  echo "[run] Arduino en $DEV"
  termux-usb -e ./phone/usb_launch.sh "$DEV"
  [ "$ONCE" -eq 1 ] && break
  [ "$STOP" -eq 1 ] && break
  echo "[run] la vision termino; reintento en 3 s (Ctrl-C para salir)"
  sleep 3
done
echo "[run] detenido"
