"""Demo en vivo: captura -> ArUco + pelota -> imagen anotada -> página web.

En el teléfono (Termux), desde la carpeta del proyecto:
    python live.py                                  # cámara 0, bucle infinito
    python live.py --show-mask --max-balls 3

En la laptop (otra terminal), túnel SSH hacia el teléfono; deja esa terminal abierta:
    ssh -N -L 8000:127.0.0.1:8000 -p 8022 <usuario>@<ip-del-telefono>
y abre  http://127.0.0.1:8000/  en el navegador.

Calibración en sitio (objeto sustituto): en la página, haz clic sobre la pelota.
Se calculan umbrales HSV nuevos a partir de esa captura (onsite.py), se aplican a
las siguientes capturas y la misma imagen se redibuja al instante.
  Reiniciar = vuelve a los parámetros con que arrancó; Guardar = ball_params_site.json
  (úsalo luego con  --ball-params ball_params_site.json).

Sin cámara (ensayo):  python live.py --images data/ball_dataset/esc0_000.jpg ...

Los tiempos del encabezado son de capture / aruco / ball. NO incluyen dibujar,
codificar el JPEG ni la máscara de --show-mask (esa se calcula aparte, solo para ver).
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time

import cv2

import link
from core import Frame
from detectors import ArucoDetector, BallDetector, BallParams
from onsite import params_from_click
from pipeline import ConsoleSink, stream
from sources import source_from_args
from debug.viz import annotate
from debug.web import start_server

INDEX = r"""<!doctype html><meta charset="utf-8"><title>Demo en vivo</title>
<style>
body{background:#14161a;color:#e8e8e8;font:15px system-ui;margin:0;padding:12px 16px}
img{max-width:100%;max-height:74vh;display:block;margin:auto;border-radius:6px;background:#222;cursor:crosshair}
#bar{text-align:center;margin:10px 0 4px}
button{background:#2a2f38;color:#e8e8e8;border:1px solid #444;border-radius:6px;padding:6px 14px;margin:0 4px;font:inherit;cursor:pointer}
button:hover{background:#363c47}
#m{text-align:center;min-height:1.4em;color:#ffd166}
#s{margin:10px auto;max-width:960px;font:13px ui-monospace,monospace;color:#9fb0c0;white-space:pre-wrap}
#c{text-align:center;color:#888;font-size:13px;margin-top:6px}
</style>
<img id="f" alt="esperando la primera captura…">
<div id="c">esperando la primera captura…</div>
<div id="bar"><button id="r">Reiniciar parámetros</button><button id="g">Guardar parámetros</button></div>
<div id="m">Haz clic sobre la pelota para calibrar con ese objeto.</div>
<pre id="s"></pre>
<script>
let last=-1;
const $=id=>document.getElementById(id);
async function post(path,body){
  const r=await fetch(path,{method:'POST',headers:{'X-Demo':'1','Content-Type':'application/json'},body:JSON.stringify(body||{})});
  return r.json();
}
$('f').addEventListener('click',async ev=>{
  const b=ev.target.getBoundingClientRect();
  const res=await post('pick',{x:(ev.clientX-b.left)/b.width,y:(ev.clientY-b.top)/b.height});
  $('m').textContent=res.ok?('Calibrado: H '+res.hsv_lower[0]+'–'+res.hsv_upper[0]+', S ≥ '+res.hsv_lower[1]+', V ≥ '+res.hsv_lower[2]
    +'  (región de '+res.area_px+' px, radio ≈ '+res.radio_equiv_px+' px)'):('No se pudo: '+res.error);
});
$('r').onclick=async()=>{const r=await post('reset');$('m').textContent=r.ok?'Parámetros reiniciados.':r.error;};
$('g').onclick=async()=>{const r=await post('save');$('m').textContent=r.ok?('Guardado en '+r.path):r.error;};
async function tick(){
  try{
    const r=await fetch('status.json?'+Date.now(),{cache:'no-store'}); const s=await r.json();
    if(s.rev!==last){ last=s.rev; $('f').src='last.jpg?'+s.rev;
      $('c').textContent='frame '+s.index+' · '+s.hora;
      $('s').textContent=Object.entries(s.timings_ms).map(([k,v])=>k+' '+v+' ms').join('   ')
        +'\nHSV pelota: '+s.params.lower.join(',')+' → '+s.params.upper.join(',')+'\n'
        +(s.detections.map(d=>d.kind+' '+d.label+' @('+d.center.join(',')+') s='+d.size).join('\n')||'sin detecciones'); }
  }catch(e){ $('c').textContent='sin conexión con el teléfono…'; }
  setTimeout(tick,600);
}
tick();
</script>"""


def atomic_write(path: str, data: bytes) -> None:
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)        # el navegador nunca ve un archivo a medias


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="*", help="ensayo sin cámara")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--camera-url", default="http://127.0.0.1:8080/shot.jpg",
                    help="foto por HTTP de una app de cámara abierta (IP Webcam); por defecto %(default)s")
    ap.add_argument("--termux-camera", action="store_true",
                    help="usar termux-camera-photo (lento, ~1.4 s) en vez de --camera-url")
    ap.add_argument("--ball-params", default="ball_params.json")
    ap.add_argument("--max-balls", type=int, default=3)
    ap.add_argument("--focal-px", type=float, default=None)
    ap.add_argument("--show-mask", action="store_true")
    ap.add_argument("--out", default="out/live")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--max-width", type=int, default=960, help="ancho del JPEG que se publica")
    ap.add_argument("--interval", type=float, default=0.0, help="pausa extra entre ciclos (s)")
    ap.add_argument("-n", type=int, default=0, help="ciclos (0 = hasta Ctrl-C)")
    ap.add_argument("--fail-tolerance", type=int, default=5)
    link.add_arguments(ap)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(INDEX)
    for stale in ("last.jpg", "status.json"):           # no mostrar una sesión anterior
        p = os.path.join(a.out, stale)
        if os.path.exists(p):
            os.remove(p)

    base = BallParams.from_json(a.ball_params) if os.path.exists(a.ball_params) else BallParams()
    base.max_results = a.max_balls
    if a.focal_px:
        base.focal_px = a.focal_px
    ball = BallDetector(base)
    aruco = ArucoDetector()
    source = source_from_args(a.images, a.camera, None if a.termux_camera else a.camera_url)

    lock = threading.Lock()
    state = {"rev": 0, "last": None}        # last = (imagen, índice, dets ArUco, tiempos)

    def publish(img, index, dets, timings):
        """Dibuja, guarda last.jpg y status.json. Llamar con `lock` tomado."""
        mask = ball.mask(Frame(img, 0.0, index))[0] if a.show_mask else None
        vis = annotate(img, dets, timings, mask, title=f"frame {index}")
        if vis.shape[1] > a.max_width:
            k = a.max_width / vis.shape[1]
            vis = cv2.resize(vis, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        _, buf = cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 80])
        atomic_write(os.path.join(a.out, "last.jpg"), buf.tobytes())
        state["rev"] += 1
        status = {
            "rev": state["rev"], "index": index, "hora": time.strftime("%H:%M:%S"),
            "timings_ms": {k: round(v * 1e3, 1) for k, v in timings.items()},
            "params": {"lower": list(ball.p.hsv_lower), "upper": list(ball.p.hsv_upper)},
            "detections": [{"kind": d.kind, "label": d.label,
                            "center": [round(d.center[0]), round(d.center[1])],
                            "size": round(d.size, 1)} for d in dets],
        }
        atomic_write(os.path.join(a.out, "status.json"), json.dumps(status).encode())

    def redraw_last():
        img, index, dets, timings = state["last"]
        bd = ball.detect(Frame(img, 0.0, index))
        publish(img, index, [d for d in dets if d.kind != "ball"] + bd, timings)

    # ---- endpoints de la página (POST) ----
    def pick(body):
        with lock:
            if state["last"] is None:
                raise ValueError("Aún no hay ninguna captura.")
            img = state["last"][0]
            h, w = img.shape[:2]
            new, info = params_from_click(img, float(body["x"]) * w, float(body["y"]) * h, base)
            ball.p = new                       # las siguientes capturas ya usan estos umbrales
            redraw_last()
        print(f"calibración por clic: {info['hsv_lower']} -> {info['hsv_upper']} (área {info['area_px']} px)")
        return {"ok": True, **info}

    def reset(_):
        with lock:
            ball.p = base
            if state["last"] is not None:
                redraw_last()
        return {"ok": True}

    def save(_):
        path = "ball_params_site.json"
        with lock:
            ball.p.to_json(path)
        print(f"parámetros guardados en {path}")
        return {"ok": True, "path": path}

    start_server(a.out, a.host, a.port, routes={"/pick": pick, "/reset": reset, "/save": save})
    print(f"Sirviendo {a.out}/ en http://{a.host}:{a.port}/   (Ctrl-C para salir)")
    print(f"Parámetros de pelota: {a.ball_params if os.path.exists(a.ball_params) else 'por defecto'}")

    console = ConsoleSink()
    arduino = link.sink_from_args(a)
    interval = max(a.interval, 0.5 if a.images else 0.0)     # con imágenes, evita un bucle desbocado
    i = 0
    try:
        for frame, r in stream(source, [aruco, ball], a.fail_tolerance, interval, lock):
            console.send(r)
            if arduino:
                arduino.send(r)
            with lock:
                state["last"] = (frame.image, frame.index, r.detections, r.timings)
                publish(frame.image, frame.index, r.detections, r.timings)
            i += 1
            if a.n and i >= a.n:
                break
    except RuntimeError as e:
        raise SystemExit(str(e))
    except KeyboardInterrupt:
        print("\nFin.")
    finally:
        if arduino:
            arduino.close()


if __name__ == "__main__":
    main()
