"""Servidor HTTP mínimo (solo biblioteca estándar) para ver resultados desde la laptop.

Escucha en 127.0.0.1 por defecto: no queda expuesto en la red del teléfono; se
accede con un túnel SSH (ver live.py). Sin caché, para que el navegador siempre
pida la imagen más reciente.
"""
from __future__ import annotations

import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class _Handler(SimpleHTTPRequestHandler):
    routes: dict = {}

    def do_POST(self):
        """POST JSON a rutas registradas. Exige la cabecera X-Demo: así otra página
        abierta en el navegador no puede disparar acciones (provocaría un preflight
        CORS que este servidor no contesta)."""
        fn = self.routes.get(self.path.split("?")[0])
        if fn is None:
            return self.send_error(404)
        try:
            if self.headers.get("X-Demo") != "1":
                raise PermissionError("falta X-Demo")
            n = int(self.headers.get("Content-Length") or 0)
            res, code = fn(json.loads(self.rfile.read(n) or b"{}")), 200
        except Exception as e:                       # el error va al navegador, no mata el servidor
            res, code = {"ok": False, "error": str(e)}, 400
        data = json.dumps(res).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):      # silencio: la consola es para los tiempos
        pass


def start_server(directory: str, host: str = "127.0.0.1", port: int = 8000, routes: dict | None = None):
    cls = type("Handler", (_Handler,), {"routes": routes or {}})
    handler = functools.partial(cls, directory=directory)
    try:
        srv = ThreadingHTTPServer((host, port), handler)
    except OSError as e:
        raise SystemExit(f"No pude abrir {host}:{port} ({e}). ¿Otro proceso lo usa? Prueba --port.")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
