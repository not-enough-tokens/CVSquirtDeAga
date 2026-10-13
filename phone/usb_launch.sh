#!/data/data/com.termux/files/usr/bin/bash
# Lanza main.py o live.py con el Arduino conectado. termux-usb entrega el file descriptor en $1.
#
#   termux-usb -r /dev/bus/usb/001/004                       # una vez: permiso
#   termux-usb -e ./phone/usb_launch.sh /dev/bus/usb/001/004
#
# Que se ejecuta lo decides en phone/usb_launch.cmd (una linea), p. ej.:
#   main.py -n 30 --ball-params ball_params.json
#   live.py --ball-params ball_params.json
# (sin el archivo: main.py -n 30 --ball-params ball_params.json). No pongas --arduino-fd: lo anade este script.
FD="$1"
cd "$(dirname "$0")/.." || exit 1
CMD="main.py -n 30 --ball-params ball_params.json"
[ -f phone/usb_launch.cmd ] && CMD="$(head -n1 phone/usb_launch.cmd)"
echo "[launch] python $CMD --arduino-fd $FD"
exec python $CMD --arduino-fd "$FD"
