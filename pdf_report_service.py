from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOST = '127.0.0.1'
PORT = 8765
VIEWPORT = {'width': 1122, 'height': 794}
BROWSER_CANDIDATES = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
]


def find_browser_binary() -> str:
    for candidate in BROWSER_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    for candidate in ('google-chrome', 'chromium', 'chromium-browser'):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError('No se encontró un navegador compatible para renderizar el PDF.')


def wrap_batch_pages(pages: list[str]) -> str:
    documents = []
    for index, page_html in enumerate(pages):
        if not isinstance(page_html, str) or '<html' not in page_html.lower():
            raise ValueError(f'La página {index + 1} no contiene un HTML válido.')
        documents.append(page_html)
    return '\n<div style="page-break-after: always;"></div>\n'.join(documents)


def render_pdf(html: str) -> bytes:
    if not html or '<html' not in html.lower():
        raise ValueError('No se recibió un documento HTML válido para renderizar.')

    browser_binary = find_browser_binary()
    with tempfile.TemporaryDirectory(prefix='fp2026_pdf_') as tmpdir:
        tmp_path = Path(tmpdir)
        html_path = tmp_path / 'report.html'
        pdf_path = tmp_path / 'report.pdf'
        html_path.write_text(html, encoding='utf-8')

        command = [
            browser_binary,
            '--headless',
            '--disable-gpu',
            '--no-sandbox',
            '--no-first-run',
            '--no-default-browser-check',
            '--virtual-time-budget=5000',
            '--run-all-compositor-stages-before-draw',
            '--no-pdf-header-footer',
            f'--window-size={VIEWPORT["width"]},{VIEWPORT["height"]}',
            f'--print-to-pdf={pdf_path}',
            html_path.as_uri(),
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0 or not pdf_path.exists():
            detail = (completed.stderr or completed.stdout or '').strip()
            if detail:
                raise RuntimeError(f'No se pudo renderizar el PDF con el navegador local: {detail}')
            raise RuntimeError('No se pudo renderizar el PDF con el navegador local.')
        return pdf_path.read_bytes()


class Handler(BaseHTTPRequestHandler):
    server_version = 'CFIPDF/2.1'

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
            self._send_json({'ok': True, 'engine': 'local-chrome-headless'})
            return
        if path == '/':
            self._send_html(
                '<!doctype html><html lang="es"><meta charset="utf-8"><title>Servicio PDF activo</title>'
                '<body style="font-family:Arial,sans-serif;padding:32px;background:#f4f7fb;color:#1c2443">'
                '<h1>Servicio PDF activo</h1><p>Motor: navegador local en modo headless</p>'
                '<ul><li><code>GET /health</code></li><li><code>POST /render</code></li></ul>'
                '</body></html>'
            )
            return
        self._send_json({'error': 'Ruta no encontrada.'}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ('/render', '/render-batch'):
            self._send_json({'error': 'Ruta no encontrada.'}, 404)
            return

        length = int(self.headers.get('Content-Length', '0') or 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode('utf-8'))
        except Exception:
            self._send_json({'error': 'No se pudo leer el cuerpo JSON.'}, 400)
            return

        if path == '/render-batch':
            pages = payload.get('pages')
            if not isinstance(pages, list) or not pages:
                self._send_json({'error': 'No se recibieron páginas HTML válidas para renderizar.'}, 400)
                return
            try:
                html = wrap_batch_pages(pages)
            except ValueError as exc:
                self._send_json({'error': str(exc)}, 400)
                return
        else:
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
    server = HTTPServer((HOST, PORT), Handler)
    print(f'Servicio PDF activo en http://{HOST}:{PORT}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    serve()
