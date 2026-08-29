#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Actualiza FP2026 directamente desde la API de PEI.

Genera el mismo datos.json que el flujo manual con Excel, pero toma los
otorgamientos desde PEI. No guarda credenciales en el repositorio: lee todo
desde variables de entorno o desde un archivo .env local.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

from generar_reportes_publicados import main as generar_reportes
from procesar_excel_cfi import (
    CODIGOS_VALIDOS,
    CUATRI_DESDE,
    CUATRI_HASTA,
    build_json,
    extraer_codigo,
    round1,
)


DEFAULT_BASE_URL = "https://pei-api.cfi.org.ar"
DEFAULT_ESTADO_ID = 26
DEFAULT_TARGET_YEAR = 2026
TIMEOUT_SECONDS = 60


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_env(name: str, default: str = "", required: bool = False) -> str:
    value = os.getenv(name, default).strip()
    if required and not value:
        raise RuntimeError(f"Falta la variable de entorno {name}")
    return value


def get_int_env(name: str, default: int) -> int:
    raw = get_env(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"La variable {name} debe ser un numero entero: {raw}") from exc


def pei_request(method: str, url: str, token: str = "", payload: dict[str, Any] | None = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} consultando {url}: {detail[:800]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"No se pudo conectar con {url}: {exc}") from exc


def request_fresh_token(base_url: str) -> str:
    api_key = get_env("PEI_CLIENT_API_KEY", required=True)
    security_id = get_env("PEI_CLIENT_SECURITY_ID", required=True)
    payload = {
        "apellido": get_env("PEI_APELLIDO", required=True),
        "displayName": get_env("PEI_DISPLAY_NAME", required=True),
        "email": get_env("PEI_EMAIL", get_env("PEI_USERNAME"), required=True),
        "nombre": get_env("PEI_NOMBRE", required=True),
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base_url}/usuarios/token",
        data=data,
        headers={
            "Content-Type": "application/json",
            "pei-api-key": api_key,
            "pei-security-id": security_id,
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            parsed = json.loads(response.read().decode("utf-8") or "{}")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} renovando token PEI: {detail[:800]}") from exc
    token = str(parsed.get("accessToken") or "").strip()
    if not token:
        raise RuntimeError("PEI no devolvio accessToken")
    return token


def resolve_token(base_url: str) -> tuple[str, str]:
    try:
        return request_fresh_token(base_url), "renovado"
    except Exception as exc:
        fallback = get_env("PEI_ACCESS_TOKEN")
        if fallback:
            print(f"AVISO: no se pudo renovar token PEI ({exc}); uso PEI_ACCESS_TOKEN.")
            return fallback, "fallback"
        raise


def parse_fecha(raw_value: Any) -> datetime | None:
    if not raw_value:
        return None
    value = str(raw_value).strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def fetch_workflow_items(base_url: str, token: str, estado_id: int, fecha_desde: str, fecha_hasta: str) -> list[dict[str, Any]]:
    payload = {
        "idEstadoAnalizado": estado_id,
        "fechaDesde": fecha_desde,
        "fechaHasta": fecha_hasta,
    }
    errors: list[str] = []
    for path in (
        "/Reportes/WorkflowAnalisisRiesgos",
        "/reportes/WorkflowAnalisisRiesgos",
        "/reportes/workflowanalisisriesgos",
    ):
        try:
            data = pei_request("POST", f"{base_url}{path}", token, payload)
            if isinstance(data, list):
                return data
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    for path in (
        f"/WorkflowAnalisisRiesgos/enbloque/{estado_id}",
        f"/workflowanalisisriesgos/enbloque/{estado_id}",
    ):
        try:
            data = pei_request("POST", f"{base_url}{path}", token, payload)
            if isinstance(data, list):
                return data
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    raise RuntimeError("No se pudo obtener WorkflowAnalisisRiesgos: " + " | ".join(errors))


def unique_key(item: dict[str, Any]) -> tuple[str, str, str, float, str]:
    return (
        str(item.get("denominacionSolicitud") or "").strip().upper(),
        str(item.get("fechaResolucion") or "").strip(),
        str(item.get("razonSocial") or "").strip().upper(),
        float(item.get("importeSolicitado") or 0),
        str(item.get("tipoAprobado") or "").strip().upper(),
    )


def build_from_api(items: list[dict[str, Any]], target_year: int):
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
    por_mes: dict[str, dict[str, float | int]] = {}
    fecha_max = None
    vistos: set[tuple[str, str, str, float, str]] = set()
    filas_2026 = 0
    duplicados = 0
    omitidos = 0

    for item in items:
        fecha = parse_fecha(item.get("fechaResolucion"))
        if not fecha or fecha.year != target_year:
            continue
        key = unique_key(item)
        if key in vistos:
            duplicados += 1
            continue
        vistos.add(key)

        codigo = extraer_codigo(item.get("denominacionSolicitud"))
        if not codigo or codigo not in por_provincia:
            omitidos += 1
            continue

        filas_2026 += 1
        fecha_max = fecha if fecha_max is None or fecha > fecha_max else fecha_max
        importe = round1(float(item.get("importeSolicitado") or 0) / 1_000_000)
        provincia = por_provincia[codigo]
        provincia["monto"] = round1(provincia["monto"] + importe)
        provincia["cantidad"] += 1

        if CUATRI_DESDE <= fecha <= CUATRI_HASTA:
            provincia["monto_cuatrimestral"] = round1(provincia["monto_cuatrimestral"] + importe)
            provincia["cantidad_cuatrimestral"] += 1

        mes_key = f"{fecha.year}-{fecha.month:02d}"
        por_mes.setdefault(mes_key, {"monto": 0.0, "cantidad": 0})
        por_mes[mes_key]["monto"] = round1(float(por_mes[mes_key]["monto"]) + importe)
        por_mes[mes_key]["cantidad"] = int(por_mes[mes_key]["cantidad"]) + 1

        provincia["items"].append(
            {
                "denominacion": item.get("denominacionSolicitud"),
                "razon_social": item.get("razonSocial"),
                "fecha_resolucion": fecha.strftime("%Y-%m-%d"),
                "usuario_resolucion": item.get("usuarioResolucion"),
                "importe": importe,
                "linea": item.get("linea"),
                "sublinea": item.get("sublinea"),
                "programa": item.get("programa"),
                "tipo_contragarantia": item.get("tipoContragarantia"),
            }
        )

    print(f"Items PEI recibidos: {len(items)}")
    print(f"Filas {target_year} usadas: {filas_2026}")
    print(f"Duplicados omitidos: {duplicados}")
    print(f"Omitidos por provincia/datos: {omitidos}")
    return por_provincia, por_mes, fecha_max


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=os.getenv("PEI_ENV_FILE", ""))
    parser.add_argument("--skip-reports", action="store_true")
    args = parser.parse_args()

    local_env = Path(args.env_file) if args.env_file else Path.home() / "ESTADISTICAS_FP/config/pei.env"
    load_env_file(local_env)

    base_url = get_env("PEI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    estado_id = get_int_env("PEI_ESTADO_ID", DEFAULT_ESTADO_ID)
    target_year = get_int_env("PEI_TARGET_YEAR", DEFAULT_TARGET_YEAR)
    fecha_desde = datetime(target_year, 1, 1, tzinfo=timezone.utc)
    fecha_hasta = datetime.now(timezone.utc)

    print("Actualizando FP2026 desde PEI")
    print(f"Base URL: {base_url}")
    print(f"Estado: {estado_id}")
    print(f"Rango: {fecha_desde.isoformat()} -> {fecha_hasta.isoformat()}")

    token, token_mode = resolve_token(base_url)
    print(f"Token PEI listo: {token_mode}")

    items = fetch_workflow_items(base_url, token, estado_id, fecha_desde.isoformat(), fecha_hasta.isoformat())
    por_provincia, por_mes, fecha_max = build_from_api(items, target_year)
    datos = build_json(por_provincia, por_mes, fecha_max)

    Path("datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "Datos generados:",
        datos["fecha_actualizacion"],
        f"${datos['total']['monto']}M",
        f"{datos['total']['creditos']} creditos",
        f"Jul-Oct ${datos['total']['monto_cuatrimestral']}M",
        f"{datos['total']['creditos_cuatrimestral']} creditos",
    )

    if not args.skip_reports:
        generar_reportes()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
