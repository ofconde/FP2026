from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

HOST = '127.0.0.1'
PORT = 8765
VIEWPORT = {'width': 1122, 'height': 794}

_BROWSER_LOCK = threading.Lock()
_PLAYWRIGHT = None
_BROWSER = None
_CONTEXT = None


def ensure_browser():
    global _PLAYWRIGHT, _BROWSER, _CONTEXT
    if _CONTEXT is not None:
        return _CONTEXT
    _PLAYWRIGHT = sync_playwright().start()
    _BROWSER = _PLAYWRIGHT.chromium.launch(headless=True)
    _CONTEXT = _BROWSER.new_context(
        viewport=VIEWPORT,
        screen=VIEWPORT,
        device_scale_factor=2,
        locale='es-AR',
        color_scheme='light',
    )
    return _CONTEXT


def shutdown_browser():
    global _PLAYWRIGHT, _BROWSER, _CONTEXT
    if _CONTEXT is not None:
        try:
            _CONTEXT.close()
        except Exception:
            pass
        _CONTEXT = None
    if _BROWSER is not None:
        try:
            _BROWSER.close()
        except Exception:
            pass
        _BROWSER = None
    if _PLAYWRIGHT is not None:
        try:
            _PLAYWRIGHT.stop()
        except Exception:
            pass
        _PLAYWRIGHT = None


def render_pdf(html: str) -> bytes:
    if not html or '<html' not in html.lower():
        raise ValueError('No se recibió un documento HTML válido para renderizar.')

    with _BROWSER_LOCK:
        context = ensure_browser()
        page = context.new_page()
        try:
            page.set_content(html, wait_until='load')
            page.emulate_media(media='print')
            page.wait_for_timeout(1200)
            return page.pdf(
                format='A4',
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,
                margin={'top': '0mm', 'right': '0mm', 'bottom': '0mm', 'left': '0mm'},
            )
        finally:
            page.close()


class Handler(BaseHTTPRequestHandler):
    server_version = 'CFIPDF/2.0'

    def _send_json(self, payload: dict, status: int = 200):
        data = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str, status: int = 200):
        data = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(data)

    def _send_pdf(self, pdf_bytes: bytes, filename: str):
        self.send_response(200)
        self.send_header('Content-Type', 'application/pdf')
        self.send_header('Content-Length', str(len(pdf_bytes)))
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
        self.wfile.write(pdf_bytes)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            self._send_json({'ok': True, 'engine': 'playwright-chromium'})
            return
        if path == '/':
            self._send_html(
                '<!doctype html><html lang="es"><meta charset="utf-8"><title>Servicio PDF activo</title>'
                '<body style="font-family:Arial,sans-serif;padding:32px;background:#f4f7fb;color:#1c2443">'
                '<h1>Servicio PDF activo</h1><p>Motor: Playwright + Chromium</p>'
                '<ul><li><code>GET /health</code></li><li><code>POST /render</code></li></ul>'
                '</body></html>'
            )
            return
        self._send_json({'error': 'Ruta no encontrada.'}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != '/render':
            self._send_json({'error': 'Ruta no encontrada.'}, 404)
            return

        length = int(self.headers.get('Content-Length', '0') or 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode('utf-8'))
        except Exception:
            self._send_json({'error': 'No se pudo leer el cuerpo JSON.'}, 400)
            return

        html = str(payload.get('html') or '')
        filename = str(payload.get('filename') or 'reporte.pdf').strip() or 'reporte.pdf'
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'

        try:
            pdf_bytes = render_pdf(html)
        except Exception as exc:
            self._send_json({'error': f'No se pudo generar el PDF: {exc}'}, 500)
            return

        self._send_pdf(pdf_bytes, filename)


def serve():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        print(f'Servicio PDF activo en http://{HOST}:{PORT}', flush=True)
        server.serve_forever()
    finally:
        server.server_close()
        shutdown_browser()


if __name__ == '__main__':
    serve()
