#!/data/data/com.termux/files/usr/bin/bash
# Lanzador unico: funciona desde cualquier carpeta, aunque se haya perdido el bit de ejecucion
# o haya cambiado el numero de dispositivo USB. Uso:  bash ~/CVSquirtDeAga/phone/run.sh
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 1
cd "$ROOT" || exit 1
chmod +x phone/*.sh phone/*.py 2>/dev/null
MARK="$HOME/.cv_vidpid"
WANT="${CV_VIDPID:-1a86:7523}"

DEV=""
for d in $(termux-usb -l | grep -o '/dev/bus/usb/[0-9]*/[0-9]*'); do
  termux-usb -r "$d" >/dev/null 2>&1
  rm -f "$MARK"
  termux-usb -e ./phone/find_arduino.py "$d" >/dev/null 2>&1
  for _ in 1 2 3 4 5 6; do [ -s "$MARK" ] && break; sleep 0.5; done
  if [ "$(cat "$MARK" 2>/dev/null)" = "$WANT" ]; then DEV="$d"; break; fi
done

if [ -z "$DEV" ]; then
  echo "[run] no encontre un dispositivo $WANT. termux-usb -l ve:"
  termux-usb -l
  exit 1
fi
echo "[run] Arduino en $DEV"
exec termux-usb -e ./phone/usb_launch.sh "$DEV"
