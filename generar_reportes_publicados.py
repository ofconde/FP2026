from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from direct_pdf_reports import build_provincial_pdf

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "datos.json"
REPORTS_DIR = ROOT / "reportes" / "2026" / "provincias"
MANIFEST_PATH = ROOT / "reportes" / "2026" / "manifest.json"


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower()).strip("-")
    return normalized or "provincia"


def build_filename(provincia: dict) -> str:
    code = str(provincia.get("codigo") or "").upper().strip() or "XX"
    slug = slugify(str(provincia.get("nombre") or code))
    return f"{code}-{slug}.pdf"


def main() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    generated = []
    for provincia in data.get("provincias") or []:
        if not (float(provincia.get("meta_anual") or 0) > 0):
            continue
        code = str(provincia.get("codigo") or "").upper().strip()
        if not code:
            continue
        filename = build_filename(provincia)
        pdf_bytes = build_provincial_pdf(data, code)
        output_path = REPORTS_DIR / filename
        output_path.write_bytes(pdf_bytes)
        generated.append(
            {
                "codigo": code,
                "nombre": provincia.get("nombre"),
                "filename": filename,
                "updated_at": data.get("fecha_actualizacion"),
            }
        )

    manifest = {
        "fecha_actualizacion": data.get("fecha_actualizacion"),
        "total_provincias": len(generated),
        "reportes": generated,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Reportes generados: {len(generated)}")
    print(f"Actualización: {data.get('fecha_actualizacion')}")


if __name__ == "__main__":
    main()
