from __future__ import annotations

import json
import io
import shutil
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from PIL import Image
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from direct_pdf_reports import build_provincial_pdf

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


def render_png(html: str) -> bytes:
    if not html or '<html' not in html.lower():
        raise ValueError('No se recibió un documento HTML válido para renderizar.')

    browser_binary = find_browser_binary()
    with tempfile.TemporaryDirectory(prefix='fp2026_pdf_') as tmpdir:
        tmp_path = Path(tmpdir)
        html_path = tmp_path / 'report.html'
        png_path = tmp_path / 'report.png'
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
            f'--window-size={VIEWPORT["width"]},{VIEWPORT["height"]}',
            f'--screenshot={png_path}',
            html_path.as_uri(),
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0 or not png_path.exists():
            detail = (completed.stderr or completed.stdout or '').strip()
            if detail:
                raise RuntimeError(f'No se pudo renderizar la lámina con el navegador local: {detail}')
            raise RuntimeError('No se pudo renderizar la lámina con el navegador local.')
        return png_path.read_bytes()


def image_bytes_to_pdf(image_bytes_list: list[bytes]) -> bytes:
    packet = io.BytesIO()
    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(packet, pagesize=(page_width, page_height))

    for image_bytes in image_bytes_list:
        image = Image.open(io.BytesIO(image_bytes))
        image_reader = ImageReader(image)
        img_width, img_height = image.size
        scale = min(page_width / img_width, page_height / img_height)
        draw_width = img_width * scale
        draw_height = img_height * scale
        offset_x = (page_width - draw_width) / 2
        offset_y = (page_height - draw_height) / 2
        pdf.drawImage(image_reader, offset_x, offset_y, width=draw_width, height=draw_height)
        pdf.showPage()

    pdf.save()
    return packet.getvalue()


def render_pdf(html: str) -> bytes:
    return image_bytes_to_pdf([render_png(html)])


def render_pdf_batch(pages: list[str]) -> bytes:
    return image_bytes_to_pdf([render_png(page_html) for page_html in pages])


class Handler(BaseHTTPRequestHandler):
    server_version = 'CFIPDF/3.0'

    def _send_cors_headers(self):
        origin = self.headers.get('Origin')
        self.send_header('Access-Control-Allow-Origin', origin or '*')
        self.send_header('Vary', 'Origin, Access-Control-Request-Private-Network')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Access-Control-Max-Age', '600')

    def _send_json(self, payload: dict, status: int = 200):
        data = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str, status: int = 200):
        data = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _send_pdf(self, pdf_bytes: bytes, filename: str):
        self.send_response(200)
        self.send_header('Content-Type', 'application/pdf')
        self.send_header('Content-Length', str(len(pdf_bytes)))
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(pdf_bytes)

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _read_payload(self):
        length = int(self.headers.get('Content-Length', '0') or 0)
        raw = self.rfile.read(length)
        content_type = (self.headers.get('Content-Type') or '').split(';', 1)[0].strip().lower()

        if content_type == 'application/json' or not content_type:
            try:
                return json.loads(raw.decode('utf-8'))
            except Exception:
                raise ValueError('No se pudo leer el cuerpo JSON.')

        if content_type == 'application/x-www-form-urlencoded':
            parsed = parse_qs(raw.decode('utf-8'), keep_blank_values=True)
            payload = {key: values[-1] if values else '' for key, values in parsed.items()}
            if 'data' in payload:
                try:
                    payload['data'] = json.loads(payload['data'])
                except Exception:
                    raise ValueError('No se pudo leer el campo data enviado por formulario.')
            return payload

        raise ValueError(f'Tipo de contenido no soportado: {content_type or "desconocido"}.')

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            self._send_json({'ok': True, 'engine': 'local-chrome-headless', 'direct_provincial': True})
            return
        if path == '/':
            self._send_html(
                '<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Servicio PDF FP2026</title>'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<style>'
                'body{margin:0;font-family:Arial,sans-serif;background:#0b1422;color:#f5f8fc;}'
                '.wrap{max-width:860px;margin:0 auto;padding:48px 24px 56px;}'
                '.card{background:#111d30;border:1px solid #223650;border-radius:20px;padding:28px 30px;box-shadow:0 18px 42px rgba(0,0,0,.18);}'
                '.eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#c7a45c;font-weight:700;}'
                'h1{font-size:40px;line-height:1.05;margin:10px 0 8px;color:#f5f8fc;}'
                'p{font-size:18px;line-height:1.6;color:#93a6c4;margin:0 0 18px;}'
                '.ok{display:inline-block;margin-top:6px;padding:8px 14px;border-radius:999px;background:#12314a;color:#8fe4ff;font-weight:700;font-size:14px;}'
                '.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:24px;}'
                '.item{background:#16253a;border:1px solid #223650;border-radius:16px;padding:16px 18px;}'
                '.item b{display:block;color:#f5f8fc;font-size:15px;margin-bottom:6px;}'
                '.item code{color:#8fe4ff;font-size:14px;}'
                '.note{margin-top:18px;font-size:14px;color:#637793;}'
                '</style></head><body><div class="wrap"><div class="card">'
                '<div class="eyebrow">CFI · Financiamiento Productivo</div>'
                '<h1>Servicio local de PDF activo</h1>'
                '<p>Este endpoint no es el dashboard. Es el motor interno que usa FP2026 para generar y descargar informes en PDF.</p>'
                '<span class="ok">127.0.0.1:8765 funcionando</span>'
                '<div class="grid">'
                '<div class="item"><b>Chequeo de estado</b><code>GET /health</code></div>'
                '<div class="item"><b>PDF HTML simple</b><code>POST /render</code></div>'
                '<div class="item"><b>PDF por páginas</b><code>POST /render-batch</code></div>'
                '<div class="item"><b>PDF provincial directo</b><code>POST /render-provincial-direct</code></div>'
                '</div>'
                '<div class="note">La interfaz principal del tablero sigue estando en ofconde.github.io/FP2026.</div>'
                '</div></div></body></html>'
            )
            return
        self._send_json({'error': 'Ruta no encontrada.'}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ('/render', '/render-batch', '/render-provincial-direct'):
            self._send_json({'error': 'Ruta no encontrada.'}, 404)
            return

        try:
            payload = self._read_payload()
        except ValueError as exc:
            self._send_json({'error': str(exc)}, 400)
            return

        pages = None
        html = ''
        if path == '/render-provincial-direct':
            province_code = str(payload.get('provinceCode') or '').strip().upper()
            data = payload.get('data')
            if not province_code:
                self._send_json({'error': 'Falta provinceCode para generar el informe provincial.'}, 400)
                return
            if not isinstance(data, dict):
                self._send_json({'error': 'Faltan los datos para generar el informe provincial.'}, 400)
                return
        elif path == '/render-batch':
            pages = payload.get('pages')
            if not isinstance(pages, list) or not pages:
                self._send_json({'error': 'No se recibieron páginas HTML válidas para renderizar.'}, 400)
                return
            for index, page_html in enumerate(pages):
                if not isinstance(page_html, str) or '<html' not in page_html.lower():
                    self._send_json({'error': f'La página {index + 1} no contiene un HTML válido.'}, 400)
                    return
        else:
            html = str(payload.get('html') or '')
        filename = str(payload.get('filename') or 'reporte.pdf').strip() or 'reporte.pdf'
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'

        try:
            if path == '/render-provincial-direct':
                pdf_bytes = build_provincial_pdf(data, province_code)
            elif pages is not None:
                pdf_bytes = render_pdf_batch(pages)
            else:
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
