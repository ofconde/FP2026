from __future__ import annotations

import io
import json
import math
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw

PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
MARGIN_X = 24
MARGIN_Y = 18

NAVY = colors.HexColor("#1C2443")
TEXT = colors.HexColor("#42506D")
MUTED = colors.HexColor("#6B7895")
LIGHT = colors.HexColor("#F4F8FB")
CARD = colors.HexColor("#FFFFFF")
BORDER = colors.HexColor("#DDE8EF")
ACCENT = colors.HexColor("#10B7E8")
ACCENT_DARK = colors.HexColor("#0C8395")
SOFT = colors.HexColor("#D7EDF6")
SOFT_2 = colors.HexColor("#EAF4F8")
TRACK = colors.HexColor("#E4EEF3")

BG_DARK = colors.HexColor("#0B1422")
PANEL_DARK = colors.HexColor("#111D30")
CARD_DARK = colors.HexColor("#16253A")
BORDER_DARK = colors.HexColor("#223650")
TEXT_LIGHT = colors.HexColor("#F5F8FC")
TEXT_SOFT = colors.HexColor("#93A6C4")
TEXT_FAINT = colors.HexColor("#637793")
ACCENT_GOLD = colors.HexColor("#C7A45C")
TRACK_DARK = colors.HexColor("#23344A")

ROOT = Path(__file__).resolve().parent
MAP_HTML = ROOT / "mapa_creditos.html"
LOGO = ROOT / "logo-cfi-color-h.png"


def normalize_key(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or ""))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return value


def province_aliases() -> dict[str, str]:
    return {
        "buenos_aires": "Buenos_Aires",
        "cordoba": "Cordoba",
        "santa_fe": "Santa_Fe",
        "entre_rios": "Entre_Rios",
        "mendoza": "Mendoza",
        "tucuman": "Tucuman",
        "misiones": "Misiones",
        "rio_negro": "Rio_Negro",
        "salta": "Salta",
        "neuquen": "Neuquen",
        "corrientes": "Corrientes",
        "jujuy": "Jujuy",
        "san_luis": "San_Luis",
        "la_rioja": "La_Rioja",
        "la_pampa": "La_Pampa",
        "chaco": "Chaco",
        "san_juan": "San_Juan",
        "tierra_del_fuego": "Tierra_del_Fuego",
        "chubut": "Chubut",
        "catamarca": "Catamarca",
        "santiago_del_estero": "Santiago_del_Estero",
        "formosa": "Formosa",
        "santa_cruz": "Santa_Cruz",
    }


def load_geojson() -> dict:
    html = MAP_HTML.read_text(encoding="utf-8")
    match = re.search(r'<script id="geojsonArgentina" type="application/json">([\s\S]*?)</script>', html)
    if not match:
        raise RuntimeError("No se pudo leer el mapa base de Argentina.")
    return json.loads(match.group(1))


def format_money_compact(value: float) -> str:
    return f"$ {value:,.1f} M".replace(",", "X").replace(".", ",").replace("X", ".")


def format_money_full_millions(value: float) -> str:
    ars = value * 1_000_000
    return f"$ {ars:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_percent(value: float, digits: int = 1) -> str:
    return f"{float(value or 0):.{digits}f}%"


def format_count(value: float) -> str:
    count = int(value or 0)
    return f"{count} crédito" if count == 1 else f"{count} créditos"


def month_name(month_number: int) -> str:
    months = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    index = max(1, int(month_number or 1)) - 1
    return months[min(index, len(months) - 1)]


def current_date_label(data: dict) -> str:
    value = data.get("fecha_actualizacion")
    if not value:
        return "-"
    normalized = str(value).replace(" ", "T")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%d/%m/%Y, %H:%M")
    except Exception:
        return str(value)


def mercator(coord):
    lon, lat = coord
    rad = math.pi / 180
    return lon, math.log(math.tan(math.pi / 4 + (lat * rad) / 2)) / rad


def walk_coords(geometry, cb):
    def visit(value):
        if isinstance(value[0], (int, float)):
            cb(value)
        else:
            for item in value:
                visit(item)
    visit(geometry["coordinates"])


def geometry_bounds(geometry: dict) -> dict[str, float]:
    points: list[tuple[float, float]] = []
    walk_coords(geometry, lambda coord: points.append(mercator(coord)))
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
    }


def create_projector_from_bounds(bounds: dict[str, float], width: float, height: float, pad: float):
    span_x = max(bounds["max_x"] - bounds["min_x"], 0.0001)
    span_y = max(bounds["max_y"] - bounds["min_y"], 0.0001)
    scale = min((width - pad * 2) / span_x, (height - pad * 2) / span_y)
    offset_x = (width - span_x * scale) / 2
    offset_y = (height - span_y * scale) / 2

    def project(coord):
        x, y = mercator(coord)
        return (
            offset_x + (x - bounds["min_x"]) * scale,
            height - (offset_y + (y - bounds["min_y"]) * scale),
        )

    return project


def expand_bounds(bounds: dict[str, float], target_width: float, target_height: float) -> dict[str, float]:
    center_x = (bounds["min_x"] + bounds["max_x"]) / 2
    center_y = (bounds["min_y"] + bounds["max_y"]) / 2
    return {
        "min_x": center_x - target_width / 2,
        "max_x": center_x + target_width / 2,
        "min_y": center_y - target_height / 2,
        "max_y": center_y + target_height / 2,
    }


def map_province_by_id(provincias: list[dict]) -> dict[str, dict]:
    aliases = province_aliases()
    by_id: dict[str, dict] = {}
    for provincia in provincias:
        key = normalize_key(provincia.get("nombre"))
        by_id[aliases.get(key, key)] = provincia
    return by_id


def draw_round_rect(pdf: canvas.Canvas, x: float, y: float, w: float, h: float, radius: float = 14,
                    fill= CARD, stroke=BORDER, line_width: float = 1):
    pdf.setFillColor(fill)
    pdf.setStrokeColor(stroke)
    pdf.setLineWidth(line_width)
    pdf.roundRect(x, y, w, h, radius, fill=1, stroke=1)


def draw_text_block(pdf: canvas.Canvas, text: str, x: float, y: float, width: float,
                    font_name: str = "Helvetica", font_size: float = 12,
                    color=TEXT, leading: float | None = None):
    leading = leading or font_size * 1.35
    pdf.setFont(font_name, font_size)
    pdf.setFillColor(color)
    text_obj = pdf.beginText(x, y)
    text_obj.setFont(font_name, font_size)
    text_obj.setLeading(leading)
    text_obj.setFillColor(color)
    for line in simpleSplit(text, font_name, font_size, width):
        text_obj.textLine(line)
    pdf.drawText(text_obj)


def draw_kpi_card(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    label: str,
    value: str,
    sub: str,
    *,
    dark: bool = False,
):
    if dark:
        draw_round_rect(pdf, x, y, w, h, fill=CARD_DARK, stroke=BORDER_DARK)
        label_color = colors.HexColor("#90D9F0")
        value_color = TEXT_LIGHT
        sub_color = TEXT_SOFT
    else:
        draw_round_rect(pdf, x, y, w, h)
        label_color = colors.HexColor("#96C9DA")
        value_color = NAVY
        sub_color = MUTED
    pdf.setFillColor(label_color)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(x + 14, y + h - 20, label.upper())
    pdf.setFillColor(value_color)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(x + 14, y + h - 48, value)
    draw_text_block(pdf, sub, x + 14, y + 18, w - 28, font_size=10.5, color=sub_color)


def draw_progress(pdf: canvas.Canvas, x: float, y: float, w: float, progress: float, *, dark: bool = False):
    pdf.setFillColor(TRACK_DARK if dark else TRACK)
    pdf.roundRect(x, y, w, 14, 7, fill=1, stroke=0)
    fill_w = max(0, min(w, w * max(progress, 0) / 100))
    pdf.setFillColor(ACCENT)
    pdf.roundRect(x, y, fill_w, 14, 7, fill=1, stroke=0)


def draw_map(pdf: canvas.Canvas, provincias: list[dict], selected_code: str, x: float, y: float, w: float, h: float):
    geojson = load_geojson()
    by_id = map_province_by_id(provincias)
    selected_feature = None
    all_points_geometry = {"type": "MultiPolygon", "coordinates": []}
    for feature in geojson["features"]:
        geometry = feature["geometry"]
        if geometry["type"] == "MultiPolygon":
            all_points_geometry["coordinates"].extend(geometry["coordinates"])
        else:
            all_points_geometry["coordinates"].append(geometry["coordinates"])
        geo_id = feature["properties"].get("id_mapa") or normalize_key(feature["properties"].get("nombre"))
        provincia = by_id.get(geo_id)
        if provincia and provincia.get("codigo") == selected_code:
            selected_feature = feature

    country_bounds = geometry_bounds(all_points_geometry)
    focus_project = create_projector_from_bounds(country_bounds, 220, 220, 18)

    draw_round_rect(pdf, x, y, w, h, radius=20, fill=CARD_DARK, stroke=BORDER_DARK)

    img_w = 240
    img_h = 240
    image = Image.new("RGBA", (img_w, img_h), (12, 22, 36, 0))
    draw = ImageDraw.Draw(image)

    def pil_feature(geometry: dict, project, origin_x: float, origin_y: float, fill_color, stroke_color, stroke_w: int):
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        fill_rgba = tuple(int(fill_color.hexval()[i:i + 2], 16) for i in (2, 4, 6)) + (255,)
        stroke_rgba = tuple(int(stroke_color.hexval()[i:i + 2], 16) for i in (2, 4, 6)) + (255,)
        for polygon in polygons:
            ring = polygon[0]
            points = [(origin_x + project(coord)[0], origin_y + project(coord)[1]) for coord in ring]
            draw.polygon(points, fill=fill_rgba, outline=stroke_rgba)
            if stroke_w > 1:
                draw.line(points + [points[0]], fill=stroke_rgba, width=stroke_w)

    draw.rounded_rectangle((0, 0, 240, 240), radius=22, fill=(14, 24, 39, 255), outline=(34, 54, 80, 255), width=1)

    for feature in geojson["features"]:
        geo_id = feature["properties"].get("id_mapa") or normalize_key(feature["properties"].get("nombre"))
        provincia = by_id.get(geo_id)
        is_selected = provincia and provincia.get("codigo") == selected_code
        has_activity = provincia and float(provincia.get("monto") or 0) > 0
        pil_feature(
            feature["geometry"],
            focus_project,
            8,
            10,
            colors.HexColor("#27B6E2") if is_selected else (colors.HexColor("#A6DFF1") if has_activity else colors.HexColor("#314662")),
            colors.HexColor("#F4FBFF") if is_selected else colors.white,
            2 if is_selected else 1,
        )

    image_buffer = io.BytesIO()
    image.save(image_buffer, format="PNG")
    image_buffer.seek(0)
    pdf.drawImage(ImageReader(image_buffer), x + 10, y + 10, width=w - 20, height=h - 20, mask="auto")


def build_provincial_pdf(data: dict, province_code: str) -> bytes:
    provincias = data.get("provincias") or []
    provincia = next((item for item in provincias if item.get("codigo") == province_code), None)
    if not provincia:
        raise ValueError("No se encontró la provincia seleccionada en los datos disponibles.")
    if not (float(provincia.get("meta_anual") or 0) > 0):
        raise ValueError(f"No se puede generar el informe porque falta el objetivo provincial de {provincia.get('nombre')}.")

    ordered = sorted(provincias, key=lambda item: float(item.get("monto") or 0), reverse=True)
    rank = next((idx + 1 for idx, item in enumerate(ordered) if item.get("codigo") == province_code), 0)
    participation = (float(provincia.get("monto") or 0) / float(data.get("total", {}).get("monto") or 1)) * 100
    avg_ticket = float(provincia.get("monto") or 0) / max(int(provincia.get("cantidad") or 0), 1)
    progress = float(provincia.get("monto") or 0) / float(provincia.get("meta_anual") or 1) * 100
    cuatr_monto = float(provincia.get("monto_cuatrimestral") or 0)
    cuatr_meta = float(provincia.get("meta_cuatrimestral") or 0)
    cuatr_creditos = int(provincia.get("cantidad_cuatrimestral") or 0)
    cuatr_progress = (cuatr_monto / cuatr_meta * 100) if cuatr_meta > 0 else 0
    cuatr_desde = str(data.get("total", {}).get("cuatrimestre_desde") or "2026-07-01")
    cuatr_hasta = str(data.get("total", {}).get("cuatrimestre_hasta") or "2026-10-31")
    note = (
        f"{provincia.get('nombre')} aporta {format_percent(participation)} del total nacional, "
        f"ocupa el puesto {rank} por monto aprobado y en el cuatrimestre muestra "
        f"{format_percent(cuatr_progress)} de avance."
    )

    packet = io.BytesIO()
    pdf = canvas.Canvas(packet, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))

    pdf.setFillColor(BG_DARK)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#102038"))
    pdf.rect(0, PAGE_HEIGHT - 56, PAGE_WIDTH, 56, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#1B2C46"))
    pdf.line(0, PAGE_HEIGHT - 56, PAGE_WIDTH, PAGE_HEIGHT - 56)

    content_x = 18
    content_y = 16
    content_w = PAGE_WIDTH - 36
    content_h = PAGE_HEIGHT - 72
    draw_round_rect(pdf, content_x, content_y, content_w, content_h, radius=18, fill=PANEL_DARK, stroke=BORDER_DARK)

    if LOGO.exists():
        pdf.drawImage(ImageReader(str(LOGO)), content_x + 18, PAGE_HEIGHT - 32, width=92, height=19, mask="auto")
    pdf.setFillColor(ACCENT_GOLD)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(content_x + 18, content_y + content_h - 22, "CONSEJO FEDERAL DE INVERSIONES · FINANCIAMIENTO PRODUCTIVO")
    pdf.setFillColor(TEXT_LIGHT)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(content_x + 18, content_y + content_h - 50, f"REPORTE EJECUTIVO FP2026 · {str(provincia.get('nombre')).upper()}")
    pdf.setFillColor(colors.HexColor("#7FB6FF"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(content_x + 18, content_y + content_h - 68, provincia.get("nombre") or "-")
    pdf.setFillColor(TEXT_SOFT)
    pdf.setFont("Helvetica", 10)
    period = f"Enero / {month_name(data.get('total', {}).get('ultimo_mes') or 1)} 2026"
    pdf.drawString(content_x + 18, content_y + content_h - 84, f"Datos al {current_date_label(data)} · {period}")

    badge_w, badge_h = 132, 56
    badge_x = content_x + content_w - badge_w - 18
    badge_y = content_y + content_h - badge_h - 14
    draw_round_rect(pdf, badge_x, badge_y, badge_w, badge_h, radius=16, fill=CARD_DARK, stroke=BORDER_DARK)
    pdf.setFillColor(colors.HexColor("#9DDCF2"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(badge_x + 12, badge_y + 40, "RANKING NACIONAL")
    pdf.setFillColor(TEXT_LIGHT)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(badge_x + 12, badge_y + 16, f"#{rank}")

    hero_y = content_y + content_h - 174
    annual_w = 250
    cuatr_w = 250
    note_w = content_w - annual_w - cuatr_w - 46
    annual_x = content_x + 18
    cuatr_x = annual_x + annual_w + 14
    note_x = cuatr_x + cuatr_w + 14
    draw_round_rect(pdf, annual_x, hero_y, annual_w, 88, radius=18, fill=CARD_DARK, stroke=BORDER_DARK)
    draw_round_rect(pdf, cuatr_x, hero_y, cuatr_w, 88, radius=18, fill=CARD_DARK, stroke=BORDER_DARK)
    draw_round_rect(pdf, note_x, hero_y, note_w, 88, radius=18, fill=colors.HexColor("#0F97BC"), stroke=colors.HexColor("#0F97BC"))

    pdf.setFillColor(colors.HexColor("#9DDCF2"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(annual_x + 16, hero_y + 60, "OBJETIVO ANUAL 2026")
    pdf.setFillColor(TEXT_LIGHT)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(annual_x + 16, hero_y + 24, format_money_compact(float(provincia.get("meta_anual") or 0)))
    draw_text_block(
        pdf,
        f"Meta asignada: {format_money_full_millions(float(provincia.get('meta_anual') or 0))}",
        annual_x + 16,
        hero_y + 10,
        annual_w - 26,
        font_size=9.5,
        color=TEXT_SOFT,
    )

    pdf.setFillColor(colors.HexColor("#9DDCF2"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(cuatr_x + 16, hero_y + 60, "OBJETIVO CUATRIMESTRAL")
    pdf.setFillColor(TEXT_LIGHT)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(cuatr_x + 16, hero_y + 24, format_money_compact(cuatr_meta))
    draw_text_block(
        pdf,
        f"Tramo {cuatr_desde} al {cuatr_hasta}",
        cuatr_x + 16,
        hero_y + 10,
        cuatr_w - 26,
        font_size=9.5,
        color=TEXT_SOFT,
    )

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(note_x + 18, hero_y + 60, "LECTURA EJECUTIVA")
    draw_text_block(pdf, note, note_x + 18, hero_y + 42, note_w - 32, font_size=10.1, color=colors.white, leading=14)

    kpi_y = hero_y - 104
    total_w = content_w - 36
    kpi_gap = 10
    kpi_w = (total_w - kpi_gap * 4) / 5
    kpi_labels = [
        ("Otorgado", format_money_compact(float(provincia.get("monto") or 0)), format_count(provincia.get("cantidad") or 0)),
        ("Cuatrimestre", format_money_compact(cuatr_monto), f"{cuatr_creditos} creditos en tramo"),
        ("Participacion nacional", format_percent(participation), "Sobre el monto total pais"),
        ("Avance anual", format_percent(progress), str(provincia.get("mensaje") or "Seguimiento anual")),
        ("Avance cuatrimestral", format_percent(cuatr_progress), str(provincia.get("mensaje_cuatrimestral") or "Seguimiento cuatrimestral")),
    ]
    for idx, (label, value, sub) in enumerate(kpi_labels):
        draw_kpi_card(pdf, content_x + 18 + idx * (kpi_w + kpi_gap), kpi_y, kpi_w, 86, label, value, sub, dark=True)

    bottom_y = content_y + 72
    bottom_h = kpi_y - bottom_y - 16
    left_main_w = 420
    right_main_w = content_w - left_main_w - 32
    left_x = content_x + 18
    right_x = left_x + left_main_w + 14

    draw_round_rect(pdf, left_x, bottom_y, left_main_w, bottom_h, radius=18, fill=CARD_DARK, stroke=BORDER_DARK)
    draw_round_rect(pdf, right_x, bottom_y + bottom_h - 112, right_main_w, 112, radius=18, fill=CARD_DARK, stroke=BORDER_DARK)
    draw_round_rect(pdf, right_x, bottom_y, right_main_w, bottom_h - 126, radius=18, fill=CARD_DARK, stroke=BORDER_DARK)

    pdf.setFillColor(TEXT_LIGHT)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(left_x + 18, bottom_y + bottom_h - 32, "PANORAMA PROVINCIAL")
    draw_text_block(pdf, "Sintesis breve de posicion, volumen y cumplimiento.", left_x + 18, bottom_y + bottom_h - 54, left_main_w - 36, font_size=10.5, color=TEXT_SOFT)

    stats_x = left_x + 18
    stats_y = bottom_y + bottom_h - 98
    primary_rows = [
        ("Provincia", str(provincia.get("nombre") or "-")),
        ("Creditos", format_count(provincia.get("cantidad") or 0)),
    ]
    left_col_x = stats_x
    right_col_x = left_x + 218
    for idx, (label, value) in enumerate(primary_rows):
        col_x = left_col_x if idx % 2 == 0 else right_col_x
        row_y = stats_y - (idx // 2) * 58
        pdf.setFillColor(colors.HexColor("#8EDBF3"))
        pdf.setFont("Helvetica-Bold", 9.5)
        pdf.drawString(col_x, row_y, label.upper())
        pdf.setFillColor(TEXT_LIGHT)
        draw_text_block(
            pdf,
            value,
            col_x,
            row_y - 16,
            170,
            font_name="Helvetica-Bold",
            font_size=12,
            color=TEXT_LIGHT,
            leading=14,
        )

    summary_y = bottom_y + 24
    summary_w = (left_main_w - 52) / 2
    draw_round_rect(pdf, left_x + 18, summary_y, summary_w, 60, radius=14, fill=colors.HexColor("#0F1C2F"), stroke=BORDER_DARK)
    draw_round_rect(pdf, left_x + 30 + summary_w, summary_y, summary_w, 60, radius=14, fill=colors.HexColor("#0F1C2F"), stroke=BORDER_DARK)

    pdf.setFillColor(colors.HexColor("#8EDBF3"))
    pdf.setFont("Helvetica-Bold", 9.2)
    pdf.drawString(left_x + 32, summary_y + 42, "PARTICIPACION")
    pdf.setFillColor(TEXT_LIGHT)
    draw_text_block(
        pdf,
        f"{format_percent(participation)} del total nacional",
        left_x + 32,
        summary_y + 20,
        summary_w - 22,
        font_name="Helvetica-Bold",
        font_size=11.6,
        color=TEXT_LIGHT,
        leading=12,
    )

    summary_right_x = left_x + 44 + summary_w
    pdf.setFillColor(colors.HexColor("#8EDBF3"))
    pdf.setFont("Helvetica-Bold", 9.2)
    pdf.drawString(summary_right_x, summary_y + 42, "TRAMO JUL-OCT")
    pdf.setFillColor(TEXT_LIGHT)
    draw_text_block(
        pdf,
        f"{format_money_compact(cuatr_monto)} · {cuatr_creditos} creditos",
        summary_right_x,
        summary_y + 22,
        summary_w - 22,
        font_name="Helvetica-Bold",
        font_size=10.8,
        color=TEXT_LIGHT,
        leading=12,
    )
    pdf.setFillColor(TEXT_SOFT)
    pdf.setFont("Helvetica", 9.2)
    pdf.drawString(summary_right_x, summary_y + 8, f"Ticket promedio: {format_money_compact(avg_ticket)}")

    top_card_y = bottom_y + bottom_h - 112
    pdf.setFillColor(TEXT_LIGHT)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(right_x + 18, top_card_y + 78, "AVANCE CONTRA OBJETIVOS")
    pdf.setFillColor(TEXT_SOFT)
    pdf.setFont("Helvetica-Bold", 8.7)
    pdf.drawString(right_x + 18, top_card_y + 52, "CUATRIM.")
    draw_progress(pdf, right_x + 68, top_card_y + 48, right_main_w - 86, cuatr_progress, dark=True)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(right_x + 18, top_card_y + 34, f"{format_money_compact(cuatr_monto)} sobre {format_money_compact(cuatr_meta)}")
    pdf.setFont("Helvetica-Bold", 8.7)
    pdf.drawString(right_x + 18, top_card_y + 20, "ANUAL")
    draw_progress(pdf, right_x + 68, top_card_y + 16, right_main_w - 86, progress, dark=True)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(right_x + 18, top_card_y + 2, f"{format_money_compact(float(provincia.get('monto') or 0))} sobre {format_money_compact(float(provincia.get('meta_anual') or 0))}")

    leader = ordered[0] if ordered else provincia
    prev_item = ordered[rank - 2] if rank > 1 and len(ordered) >= rank - 1 else None
    next_item = ordered[rank] if rank > 0 and len(ordered) > rank else None

    panel_top = bottom_y + bottom_h - 148
    panel_inner_w = right_main_w - 36
    tile_gap = 10
    tile_w = (panel_inner_w - tile_gap) / 2

    pdf.setFillColor(TEXT_LIGHT)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(right_x + 18, panel_top, "CONTEXTO NACIONAL")
    draw_text_block(
        pdf,
        f"Lectura rapida para ubicar a {provincia.get('nombre')} dentro del total pais.",
        right_x + 18,
        panel_top - 22,
        panel_inner_w,
        font_size=10.6,
        color=TEXT_SOFT,
    )

    details_y = panel_top - 52
    annual_gap = max(float(provincia.get("meta_anual") or 0) - float(provincia.get("monto") or 0), 0)

    lines = [
        ("Lider nacional", f"{str(leader.get('nombre') or '-').upper()} · {format_money_compact(float(leader.get('monto') or 0))}"),
        ("Posicion provincial", f"#{rank} · {format_percent(participation)} del total nacional"),
    ]

    for idx, (label, value) in enumerate(lines):
        row_y = details_y - idx * 22
        pdf.setStrokeColor(colors.HexColor("#223650"))
        pdf.setLineWidth(1)
        pdf.line(right_x + 18, row_y - 10, right_x + right_main_w - 18, row_y - 10)
        pdf.setFillColor(colors.HexColor("#8EDBF3"))
        pdf.setFont("Helvetica-Bold", 8.8)
        pdf.drawString(right_x + 18, row_y + 3, label.upper())
        pdf.setFillColor(TEXT_LIGHT)
        draw_text_block(
            pdf,
            value,
            right_x + 132,
            row_y + 3,
            right_main_w - 150,
            font_size=9.2,
            color=TEXT_LIGHT,
            leading=10,
        )

    pdf.setFillColor(TEXT_FAINT)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(content_x + 18, content_y + 8, "CFI · FINANCIAMIENTO PRODUCTIVO · USO INSTITUCIONAL")

    pdf.showPage()
    pdf.save()
    return packet.getvalue()
