from __future__ import annotations

import io
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

BASE_DIR = Path('/Users/omarconde/ESTADISTICAS_FP/repo_fp2026')
DATA_PATH = BASE_DIR / 'datos.json'
HOST = '127.0.0.1'
PORT = 8765
PAGE_W, PAGE_H = landscape(A4)
MARGIN_X = 28
MARGIN_Y = 22
CONTENT_W = PAGE_W - MARGIN_X * 2

BG = colors.HexColor('#F4F7FB')
NAVY = colors.HexColor('#1C2443')
CYAN = colors.HexColor('#00A7E1')
TEAL = colors.HexColor('#0C8395')
MUTED = colors.HexColor('#5E6A85')
BORDER = colors.HexColor('#DCE7ED')
LIGHT = colors.HexColor('#EAF1F4')
RED = colors.HexColor('#E6431A')
GREEN = colors.HexColor('#47B067')
YELLOW = colors.HexColor('#E99505')
WHITE = colors.white

FONT_REG = 'Helvetica'
FONT_BOLD = 'Helvetica-Bold'
FONT_HEAVY = 'Helvetica-Bold'
FONT_DISPLAY = 'Helvetica-Bold'

for name, path in [
    ('Raleway', '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'),
    ('Raleway-Bold', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'),
    ('BebasNeue', '/System/Library/Fonts/Supplemental/Impact.ttf'),
]:
    try:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont(name, path))
    except Exception:
        pass

if 'Raleway' in pdfmetrics.getRegisteredFontNames():
    FONT_REG = 'Raleway'
if 'Raleway-Bold' in pdfmetrics.getRegisteredFontNames():
    FONT_BOLD = 'Raleway-Bold'
    FONT_HEAVY = 'Raleway-Bold'
if 'BebasNeue' in pdfmetrics.getRegisteredFontNames():
    FONT_DISPLAY = 'BebasNeue'


def load_data() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text())


def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def money_m(value: float) -> str:
    return '$ {:,.1f} M'.format(float(value or 0)).replace(',', 'X').replace('.', ',').replace('X', '.')


def money_ars_from_m(value: float) -> str:
    ars = float(value or 0) * 1_000_000
    return '$ {:,.1f}'.format(ars).replace(',', 'X').replace('.', ',').replace('X', '.')


def percent(value: float, digits: int = 1) -> str:
    return f"{float(value or 0):.{digits}f}%".replace('.', ',')


def fmt_int(value: float) -> str:
    return '{:,.0f}'.format(float(value or 0)).replace(',', '.')


def safe(value: Any, fallback: str = '-') -> str:
    if value is None or value == '':
        return fallback
    return str(value)


def draw_round_rect(c: canvas.Canvas, x: float, y: float, w: float, h: float, fill=WHITE, stroke=BORDER, radius: float = 16, line_width: float = 1):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(line_width)
    c.roundRect(x, y, w, h, radius, stroke=1, fill=1)


def draw_text(c: canvas.Canvas, text: str, x: float, y: float, size: float = 12, color=NAVY, font: str = FONT_REG):
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawString(x, y, text)


def wrap_text(c: canvas.Canvas, text: str, width: float, font: str, size: float) -> list[str]:
    words = safe(text, '').split()
    if not words:
        return ['']
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f'{current} {word}'
        if c.stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def draw_paragraph(c: canvas.Canvas, text: str, x: float, y: float, width: float, size: float = 11.5, leading: float | None = None, color=MUTED, font: str = FONT_REG, max_lines: int | None = None):
    leading = leading or size * 1.35
    lines = wrap_text(c, text, width, font, size)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while c.stringWidth(last + '...', font, size) > width and last:
            last = last[:-1]
        lines[-1] = last + '...'
    c.setFont(font, size)
    c.setFillColor(color)
    yy = y
    for line in lines:
        c.drawString(x, yy, line)
        yy -= leading
    return yy


def card_label(c: canvas.Canvas, text: str, x: float, y: float):
    draw_text(c, text.upper(), x, y, 10, colors.HexColor('#96C9DA'), FONT_BOLD)


def draw_kpi_card(c: canvas.Canvas, x: float, y: float, w: float, h: float, label: str, value: str, sub: str):
    draw_round_rect(c, x, y, w, h)
    card_label(c, label, x + 14, y + h - 20)
    draw_text(c, value, x + 14, y + h - 54, 24, NAVY, FONT_DISPLAY)
    draw_paragraph(c, sub, x + 14, y + 18, w - 28, 10.5, 13, MUTED, FONT_REG, 2)


def line_break_y(start_y: float, line_index: int, leading: float) -> float:
    return start_y - line_index * leading


def header(c: canvas.Canvas, title: str, subtitle: str, stamp_label: str, stamp_value: str, stamp_sub: str):
    c.setFillColor(BG)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    draw_text(c, 'CONSEJO FEDERAL DE INVERSIONES', MARGIN_X, PAGE_H - 32, 12, CYAN, FONT_BOLD)
    draw_text(c, title.upper(), MARGIN_X, PAGE_H - 74, 34, NAVY, FONT_DISPLAY)
    draw_text(c, subtitle, MARGIN_X, PAGE_H - 104, 16, MUTED, FONT_REG)
    draw_round_rect(c, PAGE_W - MARGIN_X - 150, PAGE_H - 116, 150, 80)
    card_label(c, stamp_label, PAGE_W - MARGIN_X - 136, PAGE_H - 62)
    draw_text(c, stamp_value, PAGE_W - MARGIN_X - 136, PAGE_H - 88, 28, NAVY, FONT_DISPLAY)
    draw_paragraph(c, stamp_sub, PAGE_W - MARGIN_X - 136, PAGE_H - 108, 120, 10.5, 12, MUTED, FONT_REG, 2)


def draw_goal_and_note(c: canvas.Canvas, goal_value: str, goal_sub: str, note_text: str):
    y = PAGE_H - 248
    left_w = 380
    right_w = CONTENT_W - left_w - 18
    draw_round_rect(c, MARGIN_X, y, left_w, 110)
    card_label(c, 'Objetivo nacional 2026', MARGIN_X + 18, y + 82)
    draw_text(c, goal_value, MARGIN_X + 18, y + 40, 40, NAVY, FONT_DISPLAY)
    draw_text(c, goal_sub, MARGIN_X + 18, y + 18, 13, MUTED, FONT_REG)

    draw_round_rect(c, MARGIN_X + left_w + 18, y, right_w, 110, fill=colors.HexColor('#0F9BC7'), stroke=colors.HexColor('#0F9BC7'))
    card_label(c, 'Lectura ejecutiva', MARGIN_X + left_w + 36, y + 82)
    draw_paragraph(c, note_text, MARGIN_X + left_w + 36, y + 48, right_w - 36, 14, 19, WHITE, FONT_REG, 4)
    return y - 18


def draw_month_bars(c: canvas.Canvas, monthly: list[dict[str, Any]], x: float, y: float, w: float, h: float):
    draw_round_rect(c, x, y, w, h)
    draw_text(c, 'RITMO MENSUAL', x + 16, y + h - 24, 22, NAVY, FONT_DISPLAY)
    draw_paragraph(c, 'Monto aprobado por mes para ver aceleración, estacionalidad y brechas contra el ritmo necesario.', x + 16, y + h - 46, w - 32, 10.5, 13, MUTED, FONT_REG, 2)
    chart_x = x + 18
    chart_y = y + 26
    chart_h = h - 86
    chart_w = w - 36
    max_m = max([float(item.get('monto', 0)) for item in monthly] + [1])
    bar_gap = 10
    bar_w = (chart_w - bar_gap * (len(monthly) - 1)) / max(len(monthly), 1)
    for i, item in enumerate(monthly):
        bx = chart_x + i * (bar_w + bar_gap)
        val = float(item.get('monto', 0))
        bh = max(14, chart_h * val / max_m)
        c.setFillColor(LIGHT)
        c.roundRect(bx, chart_y, bar_w, chart_h, 8, stroke=0, fill=1)
        c.setFillColor(CYAN)
        c.roundRect(bx, chart_y, bar_w, bh, 8, stroke=0, fill=1)
        draw_text(c, safe(item.get('nombre', ''))[:3].upper(), bx, y + 10, 9, MUTED, FONT_BOLD)
        draw_text(c, fmt_int(item.get('cantidad', 0)), bx, chart_y + bh + 6, 8.5, MUTED, FONT_REG)


def draw_top_list(c: canvas.Canvas, title: str, subtitle: str, rows: list[tuple[str, str, str]], x: float, y: float, w: float, h: float):
    draw_round_rect(c, x, y, w, h)
    draw_text(c, title.upper(), x + 16, y + h - 24, 22, NAVY, FONT_DISPLAY)
    draw_paragraph(c, subtitle, x + 16, y + h - 46, w - 32, 10.5, 13, MUTED, FONT_REG, 2)
    yy = y + h - 82
    for idx, (name, meta, value) in enumerate(rows, start=1):
        if idx > 1:
            c.setStrokeColor(LIGHT)
            c.line(x + 16, yy + 12, x + w - 16, yy + 12)
        draw_text(c, f'#{idx} · {name.upper()}', x + 16, yy, 12, NAVY, FONT_BOLD)
        draw_text(c, meta, x + 16, yy - 16, 10, MUTED, FONT_REG)
        vw = c.stringWidth(value, FONT_DISPLAY, 22)
        draw_text(c, value, x + w - 16 - vw, yy - 2, 22, NAVY, FONT_DISPLAY)
        yy -= 48


def draw_bullet_panel(c: canvas.Canvas, title: str, subtitle: str, bullets: list[tuple[str, str]], x: float, y: float, w: float, h: float):
    draw_round_rect(c, x, y, w, h)
    draw_text(c, title.upper(), x + 16, y + h - 24, 22, NAVY, FONT_DISPLAY)
    draw_paragraph(c, subtitle, x + 16, y + h - 46, w - 32, 10.5, 13, MUTED, FONT_REG, 2)
    yy = y + h - 88
    for label, text in bullets:
        draw_round_rect(c, x + 16, yy - 48, w - 32, 54, fill=colors.HexColor('#F6FAFC'), stroke=colors.HexColor('#E0ECF2'), radius=12)
        card_label(c, label, x + 28, yy - 14)
        draw_paragraph(c, text, x + 28, yy - 34, w - 56, 10.8, 13, NAVY, FONT_REG, 2)
        yy -= 66


def draw_summary_chips(c: canvas.Canvas, chips: list[str], x: float, y: float, w: float, h: float):
    draw_round_rect(c, x, y, w, h)
    draw_text(c, 'SEMÁFORO TERRITORIAL', x + 16, y + h - 24, 22, NAVY, FONT_DISPLAY)
    draw_paragraph(c, 'Cobertura agregada del avance provincial para priorizar acompañamiento, asistencia y seguimiento territorial.', x + 16, y + h - 46, w - 32, 10.5, 13, MUTED, FONT_REG, 2)
    cx = x + 16
    cy = y + h - 82
    max_x = x + w - 16
    for chip in chips:
        tw = c.stringWidth(chip, FONT_REG, 11) + 26
        if cx + tw > max_x:
            cx = x + 16
            cy -= 30
        draw_round_rect(c, cx, cy - 10, tw, 22, fill=colors.HexColor('#F2F7FA'), stroke=BORDER, radius=11)
        draw_text(c, chip, cx + 12, cy - 2, 11, NAVY, FONT_REG)
        cx += tw + 8


def draw_table(c: canvas.Canvas, title: str, subtitle: str, headers: list[str], rows: list[list[str]], x: float, y: float, w: float, h: float):
    draw_round_rect(c, x, y, w, h)
    draw_text(c, title.upper(), x + 16, y + h - 24, 22, NAVY, FONT_DISPLAY)
    draw_paragraph(c, subtitle, x + 16, y + h - 46, w - 32, 10.5, 13, MUTED, FONT_REG, 2)
    table_y = y + h - 82
    col_x = [x + 16, x + w * 0.56, x + w - 20]
    draw_text(c, headers[0].upper(), col_x[0], table_y, 9.5, colors.HexColor('#96C9DA'), FONT_BOLD)
    draw_text(c, headers[1].upper(), col_x[1], table_y, 9.5, colors.HexColor('#96C9DA'), FONT_BOLD)
    hw = c.stringWidth(headers[2].upper(), FONT_BOLD, 9.5)
    draw_text(c, headers[2].upper(), col_x[2] - hw, table_y, 9.5, colors.HexColor('#96C9DA'), FONT_BOLD)
    yy = table_y - 18
    for row in rows:
        c.setStrokeColor(LIGHT)
        c.line(x + 16, yy + 12, x + w - 16, yy + 12)
        draw_paragraph(c, row[0], col_x[0], yy + 2, w * 0.46, 10.5, 12.5, NAVY, FONT_REG, 2)
        draw_text(c, row[1], col_x[1], yy, 10.5, NAVY, FONT_REG)
        vw = c.stringWidth(row[2], FONT_BOLD, 11)
        draw_text(c, row[2], col_x[2] - vw, yy, 11, NAVY, FONT_BOLD)
        yy -= 34


def draw_warning_panel(c: canvas.Canvas, rows: list[tuple[str, str, str]], x: float, y: float, w: float, h: float):
    draw_round_rect(c, x, y, w, h)
    draw_text(c, 'FOCOS DE GESTIÓN', x + 16, y + h - 24, 22, NAVY, FONT_DISPLAY)
    draw_paragraph(c, 'Provincias con menor avance relativo y mayor brecha pendiente sobre la meta anual.', x + 16, y + h - 46, w - 32, 10.5, 13, MUTED, FONT_REG, 2)
    yy = y + h - 82
    for name, meta, value in rows:
        c.setStrokeColor(LIGHT)
        c.line(x + 16, yy + 12, x + w - 16, yy + 12)
        draw_text(c, name.upper(), x + 16, yy, 11.5, NAVY, FONT_BOLD)
        draw_text(c, meta, x + 16, yy - 14, 9.8, MUTED, FONT_REG)
        vw = c.stringWidth(value, FONT_DISPLAY, 20)
        draw_text(c, value, x + w - 16 - vw, yy - 1, 20, RED, FONT_DISPLAY)
        yy -= 36


def draw_participation_panel(c: canvas.Canvas, rows: list[tuple[str, float]], x: float, y: float, w: float, h: float):
    draw_round_rect(c, x, y, w, h)
    draw_text(c, 'PARTICIPACIÓN PRINCIPAL', x + 16, y + h - 24, 22, NAVY, FONT_DISPLAY)
    draw_paragraph(c, 'Peso relativo de las provincias líderes sobre el total nacional informado.', x + 16, y + h - 46, w - 32, 10.5, 13, MUTED, FONT_REG, 2)
    yy = y + h - 88
    for code, share in rows:
        draw_text(c, code, x + 16, yy, 11.5, NAVY, FONT_BOLD)
        bar_x = x + 60
        bar_w = w - 120
        c.setFillColor(LIGHT)
        c.roundRect(bar_x, yy - 5, bar_w, 10, 5, stroke=0, fill=1)
        c.setFillColor(CYAN)
        c.roundRect(bar_x, yy - 5, max(10, bar_w * min(share, 100) / 100), 10, 5, stroke=0, fill=1)
        label = percent(share)
        lw = c.stringWidth(label, FONT_BOLD, 10.5)
        draw_text(c, label, x + w - 16 - lw, yy - 1, 10.5, NAVY, FONT_BOLD)
        yy -= 30


def national_pdf(data: dict[str, Any]) -> bytes:
    provinces = data['provincias']
    active = [p for p in provinces if float(p.get('monto', 0)) > 0]
    ordered = sorted(active, key=lambda x: float(x.get('monto', 0)), reverse=True)
    by_credits = sorted(active, key=lambda x: float(x.get('cantidad', 0)), reverse=True)
    monthly = [m for m in data.get('evolucion', []) if float(m.get('monto', 0)) > 0 or float(m.get('cantidad', 0)) > 0]
    total = data['total']
    top3 = ordered[:3]
    top_share = sum((float(p['monto']) / float(total['monto']) * 100) for p in top3) if total.get('monto') else 0
    green = sum(1 for p in active if float(p.get('porcentaje', 0)) >= 80)
    yellow = sum(1 for p in active if 50 <= float(p.get('porcentaje', 0)) < 80)
    red = sum(1 for p in active if float(p.get('porcentaje', 0)) < 50)
    avg_per_prov = float(total['monto']) / len(active) if active else 0
    avg_national = float(total['monto']) / float(total['creditos']) if total.get('creditos') else 0
    top = ordered[0] if ordered else None
    note = f"El sistema acumula {money_m(total.get('monto',0))} en {fmt_int(total.get('creditos',0))} créditos, con {len(active)} provincias alcanzadas. Las tres jurisdicciones líderes concentran {percent(top_share)} del volumen nacional informado."
    strategic_notes = [
        ('CONCENTRACIÓN', f"{top['nombre']} lidera con {money_m(top['monto'])} y explica {percent(float(top['monto'])/float(total['monto'])*100)} del total nacional." if top and total.get('monto') else 'Sin datos de liderazgo disponibles.'),
        ('CAPILARIDAD', f"{len(active)} provincias ya registran aprobaciones. El promedio operativo por provincia activa es {money_m(avg_per_prov)}."),
        ('RITMO', f"El ritmo promedio ({money_m(total.get('promedio_mensual',0))} por mes) {'se mantiene alineado' if total.get('ritmo_ok') else 'todavía queda por debajo'} de lo necesario ({money_m(total.get('necesario_por_mes',0))} por mes)."),
    ]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))

    header(c, 'Informe Nacional de Créditos CFI', f"Enero / {monthly[-1]['nombre'] if monthly else 'Mayo'} 2026 · Actualizado al {datetime.now().strftime('%d/%m/%Y, %I:%M %p').lower()}", 'Avance general', percent(total.get('porcentaje',0)), 'sobre el objetivo nacional 2026')
    after = draw_goal_and_note(c, money_m(total.get('meta',0)), f"Monto faltante para cumplir: {money_m(total.get('falta',0))}", note)

    gap = 12
    card_w = (CONTENT_W - gap * 4) / 5
    x = MARGIN_X
    y = after - 88
    kpis = [
        ('Monto nacional', money_m(total.get('monto',0)), money_ars_from_m(total.get('monto',0))),
        ('Créditos', fmt_int(total.get('creditos',0)), f"{fmt_int(total.get('creditos',0))} créditos"),
        ('Provincias alcanzadas', fmt_int(len(active)), 'Con aprobaciones en el período'),
        ('Promedio nacional', money_m(avg_national), 'Monto medio por crédito'),
        ('Necesario por mes', money_m(total.get('necesario_por_mes',0)), f"{fmt_int(total.get('meses_restantes',0))} meses restantes"),
    ]
    for label, value, sub in kpis:
        draw_kpi_card(c, x, y, card_w, 72, label, value, sub)
        x += card_w + gap

    draw_month_bars(c, monthly[:5], MARGIN_X, 54, 392, 180)
    draw_bullet_panel(c, 'Claves para decisión', 'Tres señales que una autoridad nacional querría leer primero: concentración, capilaridad y ritmo.', strategic_notes, 432, 54, CONTENT_W - 392 - 12, 180)
    draw_summary_chips(c, [f'Verdes: {green}', f'Amarillas: {yellow}', f'Rojas: {red}', f'Con actividad: {len(active)} / {len(provinces)}', f'Top 3 concentran {percent(top_share)}'], MARGIN_X, 16, CONTENT_W, 28)
    c.showPage()

    header(c, 'Apertura Territorial y Focos de Gestión', 'Desglose para seguimiento federal, concentración y rezagos de gestión.', 'Concentración top 3', percent(top_share), 'del volumen nacional acumulado')
    stat_gap = 12
    stat_w = (CONTENT_W - stat_gap * 3) / 4
    sx = MARGIN_X
    sy = PAGE_H - 148
    stats = [
        ('Promedio por provincia activa', money_m(avg_per_prov), f"{len(active)} provincias con aprobaciones"),
        ('Meta agregada activa', money_m(sum(float(p.get('meta_anual',0)) for p in active)), 'Suma de metas provinciales con actividad'),
        ('Provincia mediana', safe(ordered[len(ordered)//2]['codigo'] if ordered else '-', '-'), money_m(ordered[len(ordered)//2]['monto']) if ordered else 'Sin datos suficientes'),
        ('Cobertura operativa', percent((len(active)/max(len(provinces),1))*100), f"{len(active)} de {len(provinces)} provincias con monto"),
    ]
    for label, value, sub in stats:
        draw_kpi_card(c, sx, sy, stat_w, 72, label, value, sub)
        sx += stat_w + stat_gap

    left_rows = []
    for idx, p in enumerate(ordered[:6], start=1):
        left_rows.append((f"#{idx} · {p['nombre']}", f"{fmt_int(p['cantidad'])} créditos · {percent(p['porcentaje'])} de avance", money_m(p['monto'])))
    draw_top_list(c, 'Ranking por monto', 'Jurisdicciones con mayor volumen aprobado, combinando monto, cantidad y avance relativo.', left_rows, MARGIN_X, 250, 380, 280)

    parts = [(p['codigo'], float(p['monto']) / float(total['monto']) * 100) for p in ordered[:5]] if total.get('monto') else []
    draw_participation_panel(c, parts, 420, 332, CONTENT_W - 392, 198)

    credit_rows = []
    for idx, p in enumerate(by_credits[:6], start=1):
        credit_rows.append((f"#{idx} · {p['nombre']}", f"{money_m(p['monto'])} · {percent(float(p['monto'])/float(total['monto'])*100) if total.get('monto') else '0,0%'} del total", fmt_int(p['cantidad'])))
    draw_top_list(c, 'Mayor volumen operativo', 'Provincias con más cantidad de créditos aprobados, para ver despliegue y capilaridad.', credit_rows, MARGIN_X, 24, 380, 210)

    bottom = sorted(active, key=lambda p: float(p.get('porcentaje',0)))[:5]
    warnings = []
    for p in bottom:
        warnings.append((p['nombre'], f"{money_m(p['monto'])} otorgados · brecha {money_m(abs(float(p.get('diferencia',0))))}", percent(p.get('porcentaje',0))))
    draw_warning_panel(c, warnings, 420, 24, CONTENT_W - 392, 290)

    draw_text(c, 'CFI · Financiamiento Productivo · Uso institucional', MARGIN_X, 10, 10, colors.HexColor('#96C9DA'), FONT_BOLD)
    footer = 'Página 2 de 2 · Apertura nacional'
    fw = c.stringWidth(footer, FONT_REG, 10)
    draw_text(c, footer, PAGE_W - MARGIN_X - fw, 10, 10, MUTED, FONT_REG)

    c.save()
    return buf.getvalue()


def provincial_pdf(data: dict[str, Any], code: str) -> bytes:
    provinces = data['provincias']
    details = {d['codigo']: d for d in data.get('detalles', [])}
    p = next((item for item in provinces if item['codigo'] == code), None)
    if not p:
        raise KeyError('Provincia no encontrada')
    detail = details.get(code, {})
    items = detail.get('items', [])
    ordered = sorted(provinces, key=lambda x: float(x.get('monto', 0)), reverse=True)
    rank = next((i+1 for i, item in enumerate(ordered) if item['codigo'] == code), 0)
    share = float(p['monto']) / float(data['total']['monto']) * 100 if data['total'].get('monto') else 0
    avg = float(p['monto']) / float(p['cantidad']) if p.get('cantidad') else 0
    progress = float(p.get('porcentaje',0))
    line_counter = Counter([safe(item.get('programa')) if item.get('programa') else safe(item.get('linea')) for item in items])
    top_lines = line_counter.most_common(4)
    guarantee_counter = Counter([safe(item.get('tipo_contragarantia'), 'Sin contragarantía') for item in items])
    top_guarantees = guarantee_counter.most_common(4)
    note = f"{p['nombre']} representa {percent(share)} del total nacional otorgado durante el período informado y ocupa el puesto {rank} del ranking nacional por monto."

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    header(c, f"Informe de Créditos CFI — {p['nombre']}", f"Enero / {data['evolucion'][-1]['nombre']} 2026 · Actualizado al {datetime.now().strftime('%d/%m/%Y, %I:%M %p').lower()}", 'Ranking nacional', f'#{rank}', 'según monto otorgado acumulado')
    after = draw_goal_and_note(c, money_m(p.get('meta_anual',0)), f"Brecha pendiente: {money_m(abs(float(p.get('diferencia',0))))}", note)

    gap = 12
    card_w = (CONTENT_W - gap * 4) / 5
    x = MARGIN_X
    y = after - 88
    kpis = [
        ('Otorgado', money_m(p.get('monto',0)), f"{fmt_int(p.get('cantidad',0))} créditos"),
        ('Participación nacional', percent(share), 'Sobre el monto total país'),
        ('Avance objetivo', percent(progress), p.get('mensaje','Seguimiento de meta')),
        ('Promedio por crédito', money_m(avg), money_ars_from_m(avg)),
        ('Meta provincial', money_m(p.get('meta_anual',0)), 'Objetivo 2026'),
    ]
    for label, value, sub in kpis:
        draw_kpi_card(c, x, y, card_w, 72, label, value, sub)
        x += card_w + gap

    left_rows = []
    for idx, item in enumerate(ordered[:5], start=1):
        left_rows.append((f"#{idx} · {item['nombre']}", f"{fmt_int(item['cantidad'])} créditos · {percent(float(item['monto'])/float(data['total']['monto'])*100) if data['total'].get('monto') else '0,0%'} del total", money_m(item['monto'])))
    draw_top_list(c, 'Contexto nacional', 'Posición relativa de la provincia frente a las jurisdicciones líderes por monto otorgado.', left_rows, MARGIN_X, 76, 360, 248)

    line_rows = [[f'{name}', fmt_int(count), percent(count/max(len(items),1)*100)] for name, count in top_lines] or [['Sin datos', '-', '-']]
    draw_table(c, 'Programas / líneas dominantes', 'Apertura de la cartera provincial según programa o línea con mayor presencia.', ['Línea / Programa', 'Cant.', 'Part.'], line_rows, 404, 180, CONTENT_W - 376, 144)

    guar_rows = [[name[:42], fmt_int(count), percent(count/max(len(items),1)*100)] for name, count in top_guarantees] or [['Sin datos', '-', '-']]
    draw_table(c, 'Contragarantías principales', 'Instrumentos de garantía más frecuentes dentro de la provincia.', ['Contragarantía', 'Cant.', 'Part.'], guar_rows, 404, 24, CONTENT_W - 376, 144)

    draw_warning_panel(c, [(safe(i.get('razon_social')), f"{safe(i.get('programa') or i.get('linea'))}", money_m(i.get('importe',0))) for i in sorted(items, key=lambda x: float(x.get('importe',0)), reverse=True)[:5]], MARGIN_X, 24, 360, 236)

    draw_text(c, 'CFI · Financiamiento Productivo · Uso institucional', MARGIN_X, 10, 10, colors.HexColor('#96C9DA'), FONT_BOLD)
    footer = 'Informe provincial · 1 página'
    fw = c.stringWidth(footer, FONT_REG, 10)
    draw_text(c, footer, PAGE_W - MARGIN_X - fw, 10, 10, MUTED, FONT_REG)

    c.save()
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == '/health':
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True}).encode())
            return
        try:
            data = load_data()
            if path == '/report/national.pdf':
                content = national_pdf(data)
                filename = 'Dashboard CFI - Financiamiento Productivo 2026 - Nacional.pdf'
            elif path == '/report/provincial.pdf':
                code = parse_qs(parsed.query).get('code', [''])[0]
                content = provincial_pdf(data, code)
                province = next((p['nombre'] for p in data['provincias'] if p['codigo'] == code), code)
                filename = f'Dashboard CFI - Financiamiento Productivo 2026 - {province}.pdf'
            else:
                self.send_response(404)
                self._cors()
                self.end_headers()
                return
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/pdf')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(content)
        except KeyError as e:
            self.send_response(404)
            self._cors()
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
        except Exception as e:
            self.send_response(500)
            self._cors()
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f'PDF service listening on http://{HOST}:{PORT}')
    server.serve_forever()


if __name__ == '__main__':
    main()
