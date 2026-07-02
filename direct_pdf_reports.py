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


def draw_kpi_card(pdf: canvas.Canvas, x: float, y: float, w: float, h: float, label: str, value: str, sub: str):
    draw_round_rect(pdf, x, y, w, h)
    pdf.setFillColor(colors.HexColor("#96C9DA"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(x + 14, y + h - 20, label.upper())
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(x + 14, y + h - 48, value)
    draw_text_block(pdf, sub, x + 14, y + 18, w - 28, font_size=10.5, color=MUTED)


def draw_progress(pdf: canvas.Canvas, x: float, y: float, w: float, progress: float):
    pdf.setFillColor(TRACK)
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
    selected_bounds = geometry_bounds(selected_feature["geometry"]) if selected_feature else country_bounds
    selected_width = max(selected_bounds["max_x"] - selected_bounds["min_x"], 0.8)
    selected_height = max(selected_bounds["max_y"] - selected_bounds["min_y"], 0.8)
    focus_bounds = expand_bounds(
        selected_bounds,
        max(selected_width * 1.9, (country_bounds["max_x"] - country_bounds["min_x"]) * 0.11),
        max(selected_height * 1.9, (country_bounds["max_y"] - country_bounds["min_y"]) * 0.13),
    )
    focus_project = create_projector_from_bounds(focus_bounds, 250, 220, 12)
    inset_project = create_projector_from_bounds(country_bounds, 86, 126, 8)

    draw_round_rect(pdf, x, y, w, h, radius=18, fill=LIGHT, stroke=BORDER)

    img_w = 320
    img_h = 250
    image = Image.new("RGBA", (img_w, img_h), (248, 251, 253, 0))
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

    draw.rounded_rectangle((0, 8, 258, 238), radius=18, fill=(248, 251, 253, 255), outline=(220, 233, 240, 255), width=1)
    draw.rounded_rectangle((262, 12, 318, 144), radius=14, fill=(255, 255, 255, 255), outline=(220, 233, 240, 255), width=1)

    if selected_feature:
        pil_feature(selected_feature["geometry"], focus_project, 4, 12, colors.HexColor("#D8EBF5"), colors.HexColor("#C3DCE8"), 6)
        pil_feature(selected_feature["geometry"], focus_project, 4, 12, ACCENT, NAVY, 3)

    for feature in geojson["features"]:
        geo_id = feature["properties"].get("id_mapa") or normalize_key(feature["properties"].get("nombre"))
        provincia = by_id.get(geo_id)
        is_selected = provincia and provincia.get("codigo") == selected_code
        pil_feature(
            feature["geometry"],
            inset_project,
            268,
            18,
            NAVY if is_selected else SOFT,
            colors.white,
            2 if is_selected else 1,
        )

    image_buffer = io.BytesIO()
    image.save(image_buffer, format="PNG")
    image_buffer.seek(0)
    pdf.drawImage(ImageReader(image_buffer), x + 10, y + 14, width=w - 20, height=h - 28, mask="auto")


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
    note = (
        f"{provincia.get('nombre')} representa el {format_percent(participation)} del total nacional otorgado "
        f"y ocupa el puesto {rank} del ranking país por monto aprobado."
    )

    packet = io.BytesIO()
    pdf = canvas.Canvas(packet, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))

    pdf.setFillColor(colors.HexColor("#F5F8FB"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#EAF4FA"))
    pdf.circle(PAGE_WIDTH - 38, PAGE_HEIGHT - 24, 82, fill=1, stroke=0)

    if LOGO.exists():
        pdf.drawImage(ImageReader(str(LOGO)), MARGIN_X, PAGE_HEIGHT - 38, width=112, height=24, mask="auto")
    pdf.setFillColor(ACCENT)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(MARGIN_X, PAGE_HEIGHT - 54, "CONSEJO FEDERAL DE INVERSIONES")
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawString(MARGIN_X, PAGE_HEIGHT - 84, f"INFORME DE CREDITOS CFI - {str(provincia.get('nombre')).upper()}")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 12.5)
    period = f"Enero / {month_name(data.get('total', {}).get('ultimo_mes') or 1)} 2026"
    pdf.drawString(MARGIN_X, PAGE_HEIGHT - 104, f"{period} - Actualizado al {current_date_label(data)}")

    stamp_w, stamp_h = 122, 74
    stamp_x, stamp_y = PAGE_WIDTH - MARGIN_X - stamp_w, PAGE_HEIGHT - 110
    draw_round_rect(pdf, stamp_x, stamp_y, stamp_w, stamp_h, radius=16)
    pdf.setFillColor(colors.HexColor("#96C9DA"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(stamp_x + 14, stamp_y + 52, "RANKING PAIS")
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawString(stamp_x + 14, stamp_y + 26, f"#{rank}")

    hero_y = PAGE_HEIGHT - 210
    left_w = 360
    right_w = PAGE_WIDTH - MARGIN_X * 2 - left_w - 14
    draw_round_rect(pdf, MARGIN_X, hero_y, left_w, 86, radius=18)
    draw_round_rect(pdf, MARGIN_X + left_w + 14, hero_y, right_w, 86, radius=18, fill=colors.HexColor("#139CC8"), stroke=colors.HexColor("#139CC8"))
    pdf.setFillColor(colors.HexColor("#96C9DA"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(MARGIN_X + 18, hero_y + 58, "OBJETIVO PROVINCIAL 2026")
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 30)
    pdf.drawString(MARGIN_X + 18, hero_y + 24, format_money_compact(float(provincia.get("meta_anual") or 0)))
    draw_text_block(pdf, f"Equivale a {format_money_full_millions(float(provincia.get('meta_anual') or 0))} como meta anual asignada.", MARGIN_X + 18, hero_y + 10, left_w - 30, font_size=10.5, color=MUTED)

    note_x = MARGIN_X + left_w + 14
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(note_x + 18, hero_y + 58, "LECTURA EJECUTIVA")
    draw_text_block(pdf, note, note_x + 18, hero_y + 40, right_w - 36, font_size=12, color=colors.white, leading=17)

    kpi_y = hero_y - 102
    total_w = PAGE_WIDTH - MARGIN_X * 2
    kpi_gap = 10
    kpi_w = (total_w - kpi_gap * 4) / 5
    kpi_labels = [
        ("Otorgado", format_money_compact(float(provincia.get("monto") or 0)), format_count(provincia.get("cantidad") or 0)),
        ("Participacion nacional", format_percent(participation), "Sobre el monto total pais"),
        ("Avance objetivo", format_percent(progress), f"Brecha: {format_money_compact(abs(float(provincia.get('diferencia') or 0)))}"),
        ("Promedio por credito", format_money_compact(avg_ticket), format_money_full_millions(avg_ticket)),
        ("Estado actual", format_percent(float(provincia.get("porcentaje") or 0)), str(provincia.get("mensaje") or "Seguimiento de meta")),
    ]
    for idx, (label, value, sub) in enumerate(kpi_labels):
        draw_kpi_card(pdf, MARGIN_X + idx * (kpi_w + kpi_gap), kpi_y, kpi_w, 86, label, value, sub)

    main_y = 76
    main_h = kpi_y - main_y - 16
    left_main_w = 430
    right_main_w = total_w - left_main_w - 14
    draw_round_rect(pdf, MARGIN_X, main_y, left_main_w, main_h, radius=18)
    draw_round_rect(pdf, MARGIN_X + left_main_w + 14, main_y + main_h - 112, right_main_w, 112, radius=18)
    draw_round_rect(pdf, MARGIN_X + left_main_w + 14, main_y, right_main_w, main_h - 126, radius=18)

    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(MARGIN_X + 18, main_y + main_h - 34, "MAPA TERRITORIAL")
    draw_text_block(pdf, "Foco provincial con localizador nacional para lectura institucional rapida.", MARGIN_X + 18, main_y + main_h - 56, left_main_w - 36, font_size=11.5, color=MUTED)
    draw_map(pdf, provincias, province_code, MARGIN_X + 18, main_y + 34, left_main_w - 36, main_h - 126)
    chip_y = main_y + 12
    for idx, (label, chip_color) in enumerate([(provincia.get("nombre"), ACCENT), ("Localizador nacional", NAVY), ("Entorno regional", colors.HexColor("#96C9DA"))]):
        chip_x = MARGIN_X + 18 + idx * 118
        pdf.setFillColor(LIGHT)
        pdf.setStrokeColor(BORDER)
        pdf.roundRect(chip_x, chip_y, 108, 20, 10, fill=1, stroke=1)
        pdf.setFillColor(chip_color)
        pdf.circle(chip_x + 10, chip_y + 10, 3.5, fill=1, stroke=0)
        pdf.setFillColor(TEXT)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(chip_x + 18, chip_y + 7, str(label)[:17].upper())

    right_x = MARGIN_X + left_main_w + 14
    top_card_y = main_y + main_h - 112
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(right_x + 18, top_card_y + 78, "AVANCE CONTRA OBJETIVO")
    draw_text_block(pdf, "Comparacion directa entre monto aprobado acumulado y meta provincial 2026.", right_x + 18, top_card_y + 54, right_main_w - 36, font_size=11.5, color=MUTED)
    draw_progress(pdf, right_x + 18, top_card_y + 34, right_main_w - 36, progress)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 10.5)
    pdf.drawString(right_x + 18, top_card_y + 18, f"Otorgado: {format_money_compact(float(provincia.get('monto') or 0))}")
    pdf.drawRightString(right_x + right_main_w - 18, top_card_y + 18, f"Meta: {format_money_compact(float(provincia.get('meta_anual') or 0))}")

    list_y = main_y
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(right_x + 18, list_y + main_h - 162, "TOP PROVINCIAS")
    draw_text_block(pdf, f"Contexto nacional para leer la posicion relativa de {provincia.get('nombre')}.", right_x + 18, list_y + main_h - 184, right_main_w - 36, font_size=11.5, color=MUTED)
    start_y = list_y + main_h - 218
    for idx, item in enumerate(ordered[:5]):
        row_y = start_y - idx * 54
        pdf.setStrokeColor(colors.HexColor("#ECF2F5"))
        pdf.setLineWidth(1)
        pdf.line(right_x + 18, row_y - 10, right_x + right_main_w - 18, row_y - 10)
        pdf.setFillColor(NAVY)
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(right_x + 18, row_y + 4, f"#{idx + 1} - {str(item.get('nombre')).upper()}")
        share = (float(item.get("monto") or 0) / float(data.get("total", {}).get("monto") or 1)) * 100
        draw_text_block(pdf, f"{format_count(item.get('cantidad') or 0)} - {format_percent(share)} del total", right_x + 18, row_y - 14, 210, font_size=10, color=MUTED)
        pdf.setFillColor(NAVY)
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawRightString(right_x + right_main_w - 18, row_y - 2, format_money_compact(float(item.get("monto") or 0)))

    pdf.setFillColor(colors.HexColor("#96C9DA"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(MARGIN_X, 14, "CFI - FINANCIAMIENTO PRODUCTIVO - USO INSTITUCIONAL")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(PAGE_WIDTH - MARGIN_X, 14, "Generado directamente desde datos 2026")

    pdf.showPage()
    pdf.save()
    return packet.getvalue()
