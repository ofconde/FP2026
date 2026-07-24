#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Actualiza el tablero FP2026 a partir del reporte de otorgamientos.

- Usa solo resoluciones del año 2026.
- Respeta el corte cuatrimestral jul-oct 2026.
- Mantiene el formato real de datos.json usado por la web actual.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import openpyxl


METAS_ANUALES = {
    "BA": 57000.0,
    "ER": 13100.0,
    "CO": 21000.0,
    "SF": 22000.0,
    "MZ": 12000.0,
    "SA": 4100.0,
    "MI": 4500.0,
    "TU": 4300.0,
    "RN": 15000.0,
    "NQ": 9100.0,
    "CT": 10000.0,
    "CH": 4300.0,
    "LR": 6000.0,
    "CA": 3000.0,
    "JU": 3500.0,
    "SL": 6000.0,
    "LP": 4200.0,
    "SJ": 4000.0,
    "TF": 4100.0,
    "CB": 3500.0,
    "SC": 1300.0,
    "SE": 1300.0,
    "FO": 1000.0,
}

METAS_CUATRI = {
    "BA": 19333.3,
    "ER": 6666.7,
    "CO": 7333.3,
    "SF": 7333.3,
    "MZ": 4000.0,
    "SA": 1333.3,
    "MI": 1833.3,
    "TU": 1500.0,
    "RN": 5000.0,
    "NQ": 3033.3,
    "CT": 5000.0,
    "CH": 1433.3,
    "LR": 2000.0,
    "CA": 1333.3,
    "JU": 1333.3,
    "SL": 2000.0,
    "LP": 1500.0,
    "SJ": 1333.3,
    "TF": 1333.3,
    "CB": 1333.3,
    "SC": 433.3,
    "SE": 3333.3,
    "FO": 333.3,
}

NOMBRES = {
    "BA": "Buenos Aires",
    "ER": "Entre Ríos",
    "CO": "Córdoba",
    "SF": "Santa Fe",
    "MZ": "Mendoza",
    "SA": "Salta",
    "MI": "Misiones",
    "TU": "Tucumán",
    "RN": "Río Negro",
    "NQ": "Neuquén",
    "CT": "Corrientes",
    "CH": "Chaco",
    "LR": "La Rioja",
    "CA": "Catamarca",
    "JU": "Jujuy",
    "SL": "San Luis",
    "LP": "La Pampa",
    "SJ": "San Juan",
    "TF": "Tierra del Fuego",
    "CB": "Chubut",
    "SC": "Santa Cruz",
    "SE": "Santiago del Estero",
    "FO": "Formosa",
}

CODIGOS_VALIDOS = list(METAS_ANUALES.keys())
MAPEO_CODIGOS = {codigo: codigo for codigo in CODIGOS_VALIDOS}
CUATRI_DESDE = datetime(2026, 7, 1)
CUATRI_HASTA = datetime(2026, 10, 31, 23, 59, 59)
META_TOTAL_ANUAL = round(sum(METAS_ANUALES.values()), 1)
META_TOTAL_CUATRI = 80066.7


def round1(value: float) -> float:
    return round(float(value or 0), 1)


def format_pct(value: float) -> str:
    return f"{round1(value):.0f}%"


def buscar_excel_mas_reciente() -> str | None:
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        return sys.argv[1]

    patrones = [
        "CircuitoOtorgamiento-Reporte_export_*.xlsx",
        "/Users/omarconde/Downloads/CircuitoOtorgamiento-Reporte_export_*.xlsx",
    ]
    candidatos: list[str] = []
    for patron in patrones:
        candidatos.extend(glob.glob(patron))
    if not candidatos:
        return None
    return max(candidatos, key=os.path.getmtime)


def parse_fecha(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def extraer_codigo(denominacion: str | None) -> str | None:
    if not denominacion:
        return None
    partes = str(denominacion).split("-")
    if len(partes) < 3:
        return None
    return MAPEO_CODIGOS.get(partes[2].upper())


def estado_anual(pct: float, monto: float) -> tuple[str, str, str]:
    if monto <= 0:
        return "gris", "⚫", "Sin monto aprobado"
    if pct >= 100:
        return "verde", "🟢", f"Cumplimiento anual {format_pct(pct)}"
    if pct >= 50:
        return "amarillo", "🟡", f"Cumplimiento anual {format_pct(pct)}"
    return "rojo", "🔴", f"Cumplimiento anual {format_pct(pct)}"


def estado_cuatrimestral(pct: float, monto: float) -> tuple[str, str, str]:
    if monto <= 0:
        return "rojo", "🔴", "Cumplimiento cuatrimestral 0%"
    if pct >= 80:
        return "verde", "🟢", f"Cumplimiento cuatrimestral {format_pct(pct)}"
    if pct >= 50:
        return "amarillo", "🟡", f"Cumplimiento cuatrimestral {format_pct(pct)}"
    return "rojo", "🔴", f"Cumplimiento cuatrimestral {format_pct(pct)}"


def procesar_excel(ruta_archivo: str):
    wb = openpyxl.load_workbook(ruta_archivo, read_only=True, data_only=True)
    ws = wb.active

    por_provincia = {
        codigo: {
            "monto": 0.0,
            "cantidad": 0,
            "monto_cuatrimestral": 0.0,
            "cantidad_cuatrimestral": 0,
            "items": [],
        }
        for codigo in CODIGOS_VALIDOS
    }
    por_mes = defaultdict(lambda: {"monto": 0.0, "cantidad": 0})
    fecha_max = None
    filas_2026 = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        denominacion = row[0] if len(row) > 0 else None
        fecha = parse_fecha(row[5] if len(row) > 5 else None)
        if not fecha or fecha.year != 2026:
            continue

        codigo = extraer_codigo(denominacion)
        if not codigo:
            continue

        filas_2026 += 1
        fecha_max = fecha if fecha_max is None or fecha > fecha_max else fecha_max

        importe = round1((row[7] if len(row) > 7 else 0) / 1_000_000)
        provincia = por_provincia[codigo]
        provincia["monto"] = round1(provincia["monto"] + importe)
        provincia["cantidad"] += 1

        if CUATRI_DESDE <= fecha <= CUATRI_HASTA:
            provincia["monto_cuatrimestral"] = round1(provincia["monto_cuatrimestral"] + importe)
            provincia["cantidad_cuatrimestral"] += 1

        mes_key = f"{fecha.year}-{fecha.month:02d}"
        por_mes[mes_key]["monto"] = round1(por_mes[mes_key]["monto"] + importe)
        por_mes[mes_key]["cantidad"] += 1

        provincia["items"].append(
            {
                "denominacion": denominacion,
                "razon_social": row[2] if len(row) > 2 else None,
                "fecha_resolucion": fecha.strftime("%Y-%m-%d"),
                "usuario_resolucion": row[6] if len(row) > 6 else None,
                "importe": importe,
                "linea": row[9] if len(row) > 9 else None,
                "sublinea": row[10] if len(row) > 10 else None,
                "programa": row[11] if len(row) > 11 else None,
                "tipo_contragarantia": row[12] if len(row) > 12 else None,
            }
        )

    wb.close()
    return por_provincia, por_mes, fecha_max, filas_2026


def build_evolucion(por_mes):
    nombres = {
        1: "Enero",
        2: "Febrero",
        3: "Marzo",
        4: "Abril",
        5: "Mayo",
        6: "Junio",
        7: "Julio",
        8: "Agosto",
        9: "Septiembre",
        10: "Octubre",
        11: "Noviembre",
        12: "Diciembre",
    }
    evolucion = []
    for key in sorted(por_mes.keys()):
        year, month = key.split("-")
        month_num = int(month)
        evolucion.append(
            {
                "mes": month_num,
                "nombre": nombres[month_num],
                "monto": round1(por_mes[key]["monto"]),
                "cantidad": int(por_mes[key]["cantidad"]),
            }
        )
    return evolucion


def build_json(por_provincia, por_mes, fecha_max):
    ultimo_mes = max((item["mes"] for item in build_evolucion(por_mes)), default=1)
    monto_total = round1(sum(item["monto"] for item in por_provincia.values()))
    creditos_total = sum(item["cantidad"] for item in por_provincia.values())
    monto_cuatri = round1(sum(item["monto_cuatrimestral"] for item in por_provincia.values()))
    creditos_cuatri = sum(item["cantidad_cuatrimestral"] for item in por_provincia.values())
    falta = round1(META_TOTAL_ANUAL - monto_total)
    meses_restantes = max(0, 12 - ultimo_mes)
    promedio_mensual = round1(monto_total / ultimo_mes if ultimo_mes else 0)
    necesario_por_mes = round1(falta / meses_restantes if meses_restantes else 0)

    provincias = []
    detalles = []
    for codigo in CODIGOS_VALIDOS:
        monto = round1(por_provincia[codigo]["monto"])
        cantidad = int(por_provincia[codigo]["cantidad"])
        meta_anual = METAS_ANUALES[codigo]
        pct_anual = round1((monto / meta_anual) * 100 if meta_anual else 0)
        estado, icono, mensaje = estado_anual(pct_anual, monto)

        monto_c = round1(por_provincia[codigo]["monto_cuatrimestral"])
        cantidad_c = int(por_provincia[codigo]["cantidad_cuatrimestral"])
        meta_c = METAS_CUATRI[codigo]
        pct_c = round1((monto_c / meta_c) * 100 if meta_c else 0)
        estado_c, icono_c, mensaje_c = estado_cuatrimestral(pct_c, monto_c)

        resumen = {
            "codigo": codigo,
            "nombre": NOMBRES[codigo],
            "monto": monto,
            "cantidad": cantidad,
            "meta_anual": meta_anual,
            "diferencia": round1(monto - meta_anual),
            "porcentaje": pct_anual,
            "estado": estado,
            "icono": icono,
            "mensaje": mensaje,
            "meta_cuatrimestral": meta_c,
            "monto_cuatrimestral": monto_c,
            "cantidad_cuatrimestral": cantidad_c,
            "porcentaje_cuatrimestral": pct_c,
            "estado_cuatrimestral": estado_c,
            "icono_cuatrimestral": icono_c,
            "mensaje_cuatrimestral": mensaje_c,
        }
        provincias.append(resumen)

        items = sorted(
            por_provincia[codigo]["items"],
            key=lambda item: (item["fecha_resolucion"], item["denominacion"] or ""),
            reverse=True,
        )
        detalles.append(
            {
                "codigo": codigo,
                "nombre": NOMBRES[codigo],
                "monto": monto,
                "cantidad": cantidad,
                "meta_anual": meta_anual,
                "porcentaje": pct_anual,
                "meta_cuatrimestral": meta_c,
                "monto_cuatrimestral": monto_c,
                "cantidad_cuatrimestral": cantidad_c,
                "porcentaje_cuatrimestral": pct_c,
                "estado_cuatrimestral": estado_c,
                "mensaje_cuatrimestral": mensaje_c,
                "items": items,
            }
        )

    provincias.sort(key=lambda item: item["monto"], reverse=True)
    detalles.sort(key=lambda item: item["monto"], reverse=True)

    return {
        "fecha_actualizacion": (fecha_max or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
        "total": {
            "monto": monto_total,
            "creditos": creditos_total,
            "porcentaje": round1((monto_total / META_TOTAL_ANUAL) * 100 if META_TOTAL_ANUAL else 0),
            "meta": META_TOTAL_ANUAL,
            "falta": falta,
            "meses_restantes": meses_restantes,
            "promedio_mensual": promedio_mensual,
            "necesario_por_mes": necesario_por_mes,
            "ritmo_ok": promedio_mensual >= necesario_por_mes if meses_restantes else True,
            "ultimo_mes": ultimo_mes,
            "meta_cuatrimestral": META_TOTAL_CUATRI,
            "monto_cuatrimestral": monto_cuatri,
            "creditos_cuatrimestral": creditos_cuatri,
            "porcentaje_cuatrimestral": round1((monto_cuatri / META_TOTAL_CUATRI) * 100 if META_TOTAL_CUATRI else 0),
            "cuatrimestre_iniciado": True,
            "cuatrimestre_desde": "2026-07-01",
            "cuatrimestre_hasta": "2026-10-31",
        },
        "provincias": provincias,
        "evolucion": build_evolucion(por_mes),
        "detalles": detalles,
    }


def main():
    archivo = buscar_excel_mas_reciente()
    if not archivo:
        print("No encontré un Excel para procesar.")
        sys.exit(1)

    por_provincia, por_mes, fecha_max, filas_2026 = procesar_excel(archivo)
    datos = build_json(por_provincia, por_mes, fecha_max)
    Path("datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Excel procesado: {archivo}")
    print(f"Filas 2026: {filas_2026}")
    print(f"Actualización: {datos['fecha_actualizacion']}")
    print(
        "Total:",
        f"${datos['total']['monto']}M",
        f"{datos['total']['creditos']} créditos",
        f"Jul-Oct ${datos['total']['monto_cuatrimestral']}M",
        f"{datos['total']['creditos_cuatrimestral']} créditos",
    )


if __name__ == "__main__":
    main()
