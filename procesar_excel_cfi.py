#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para procesar Excel de CFI y generar datos.json para dashboard GitHub Pages
Autor: CFI - Omar Conde
Fecha: Abril 2026
"""

import openpyxl
import json
from datetime import datetime
from collections import defaultdict
import glob
import os

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# Metas 2026 por provincia (millones de pesos - ANUAL)
METAS_2026 = {
    'BA': 56830, 'SF': 21510, 'CO': 20755, 'CB': 20755, 'ER': 13066,
    'MZ': 11812, 'CT': 10326, 'CS': 10326, 'NQ': 9053, 'SL': 5743, 
    'LR': 5373, 'MI': 4435, 'CH': 4334, 'HA': 4334, 'TU': 4310, 
    'LP': 4206, 'SA': 4143, 'TF': 4118, 'RN': 3565, 'HU': 3527, 
    'JU': 3430, 'CA': 2937, 'SJ': 2418, 'SE': 1660, 'SC': 1350, 
    'FO': 1098
}

NOMBRES_PROVINCIAS = {
    'BA': 'Buenos Aires', 'SF': 'Santa Fe', 'CO': 'Córdoba', 'CB': 'Córdoba',
    'ER': 'Entre Ríos', 'MZ': 'Mendoza', 'CT': 'Corrientes', 'CS': 'Corrientes',
    'NQ': 'Neuquén', 'SL': 'San Luis', 'LR': 'La Rioja', 'MI': 'Misiones',
    'CH': 'Chaco', 'HA': 'Chaco', 'TU': 'Tucumán', 'LP': 'La Pampa',
    'SA': 'Salta', 'TF': 'Tierra del Fuego', 'RN': 'Río Negro',
    'HU': 'Chubut', 'JU': 'Jujuy', 'CA': 'Catamarca', 'SJ': 'San Juan',
    'SE': 'Santiago del Estero', 'SC': 'Santa Cruz', 'FO': 'Formosa'
}

META_TOTAL = 207006  # Millones de pesos

# ============================================================================
# FUNCIONES
# ============================================================================

def buscar_excel_mas_reciente():
    """Busca el archivo Excel más reciente que coincida con el patrón"""
    patron = "CircuitoOtorgamiento-Reporte_export_*.xlsx"
    archivos = glob.glob(patron)
    
    if not archivos:
        print(f"❌ No se encontró ningún archivo con el patrón: {patron}")
        print(f"📂 Directorio actual: {os.getcwd()}")
        print(f"📄 Archivos disponibles:")
        for f in glob.glob("*.xlsx"):
            print(f"   - {f}")
        return None
    
    # Ordenar por fecha de modificación (más reciente primero)
    archivo_mas_reciente = max(archivos, key=os.path.getmtime)
    print(f"✓ Archivo encontrado: {archivo_mas_reciente}")
    return archivo_mas_reciente

def extraer_codigo_provincia(denominacion):
    """Extrae el código de provincia de denominacionSolicitud"""
    if not denominacion:
        return None
    
    # Formato: 2023-CR-LR-000005
    partes = str(denominacion).split('-')
    if len(partes) >= 3:
        return partes[2].upper()
    return None

def procesar_excel(ruta_archivo):
    """Procesa el Excel y devuelve los datos estructurados"""
    print(f"\n📊 Procesando archivo: {ruta_archivo}")
    
    # Abrir Excel
    wb = openpyxl.load_workbook(ruta_archivo, read_only=True, data_only=True)
    sheet = wb.active
    
    # Leer todas las filas
    datos_2026 = []
    por_provincia = defaultdict(lambda: {'monto': 0, 'cantidad': 0})
    por_mes = defaultdict(lambda: {'monto': 0, 'cantidad': 0})
    
    total_filas = 0
    filas_2026 = 0
    
    for row in sheet.iter_rows(min_row=2, values_only=True):
        total_filas += 1
        
        # Columnas (0-indexed):
        # 0: denominacionSolicitud
        # 5: fechaResolucion
        # 7: importeSolicitado
        
        denominacion = row[0] if len(row) > 0 else None
        fecha_resolucion = row[5] if len(row) > 5 else None
        importe = row[7] if len(row) > 7 else 0
        
        # Filtrar solo 2026
        if fecha_resolucion:
            try:
                if isinstance(fecha_resolucion, str):
                    fecha = datetime.fromisoformat(fecha_resolucion.replace('Z', '+00:00'))
                else:
                    fecha = fecha_resolucion
                
                año = fecha.year
                mes = fecha.month
                
                if año == 2026:
                    filas_2026 += 1
                    
                    # Convertir monto a float
                    try:
                        monto = float(importe) if importe else 0
                    except:
                        monto = 0
                    
                    # Extraer provincia
                    cod_provincia = extraer_codigo_provincia(denominacion)
                    
                    if cod_provincia:
                        por_provincia[cod_provincia]['monto'] += monto
                        por_provincia[cod_provincia]['cantidad'] += 1
                    
                    # Agrupar por mes
                    mes_key = f"{año}-{mes:02d}"
                    por_mes[mes_key]['monto'] += monto
                    por_mes[mes_key]['cantidad'] += 1
                    
            except Exception as e:
                pass  # Ignorar filas con fechas inválidas
    
    wb.close()
    
    print(f"✓ Total filas procesadas: {total_filas}")
    print(f"✓ Filas 2026: {filas_2026}")
    print(f"✓ Provincias con datos: {len(por_provincia)}")
    
    return por_provincia, por_mes

def calcular_indicadores(por_provincia, por_mes):
    """Calcula todos los indicadores del dashboard"""
    
    # Calcular totales
    monto_total = sum(p['monto'] for p in por_provincia.values())
    creditos_total = sum(p['cantidad'] for p in por_provincia.values())
    
    # Convertir a millones
    monto_total_m = monto_total / 1_000_000
    
    # Calcular progreso
    porcentaje = (monto_total_m / META_TOTAL) * 100
    falta = META_TOTAL - monto_total_m
    
    # Mes actual (detectar automáticamente del último mes con datos)
    meses_con_datos = sorted([k for k in por_mes.keys()])
    if meses_con_datos:
        ultimo_mes = int(meses_con_datos[-1].split('-')[1])
    else:
        ultimo_mes = 4  # Default: Abril
    
    meses_transcurridos = ultimo_mes
    meses_restantes = 12 - ultimo_mes
    
    # Promedio mensual
    promedio_mensual = monto_total_m / meses_transcurridos if meses_transcurridos > 0 else 0
    
    # Necesario por mes
    necesario_por_mes = falta / meses_restantes if meses_restantes > 0 else 0
    
    # Ritmo
    ritmo_ok = promedio_mensual >= necesario_por_mes
    
    return {
        'monto': round(monto_total_m, 1),
        'creditos': creditos_total,
        'porcentaje': round(porcentaje, 1),
        'meta': META_TOTAL,
        'falta': round(falta, 1),
        'meses_restantes': meses_restantes,
        'promedio_mensual': round(promedio_mensual, 1),
        'necesario_por_mes': round(necesario_por_mes, 1),
        'ritmo_ok': ritmo_ok,
        'ultimo_mes': ultimo_mes
    }

def generar_semaforo_provincias(por_provincia, mes_actual):
    """Genera los datos del semáforo por provincia"""
    
    provincias_data = []
    
    # Procesar todas las provincias con meta
    todas_provincias = set(METAS_2026.keys())
    
    for cod_prov in todas_provincias:
        data = por_provincia.get(cod_prov, {'monto': 0, 'cantidad': 0})
        
        monto_m = data['monto'] / 1_000_000
        cantidad = data['cantidad']
        
        meta_anual = METAS_2026.get(cod_prov, 0)
        objetivo_mes = (meta_anual / 12) * mes_actual
        
        # Calcular estado
        if meta_anual > 0 and objetivo_mes > 0:
            diff = monto_m - objetivo_mes
            pct = (monto_m / objetivo_mes) * 100
            diff_pct = (diff / objetivo_mes) * 100
            
            if pct >= 110:
                estado = 'verde'
                icono = '🟢'
                mensaje = f"Superó el objetivo en {abs(diff_pct):.0f}%"
            elif pct >= 90:
                estado = 'amarillo'
                icono = '🟡'
                if diff >= 0:
                    mensaje = f"Cumplió el objetivo (+{diff_pct:.0f}%)"
                else:
                    mensaje = f"Falta {abs(diff_pct):.0f}% para el objetivo"
            elif pct > 0:
                estado = 'rojo'
                icono = '🔴'
                mensaje = f"Falta {abs(diff_pct):.0f}% para el objetivo"
            else:
                estado = 'gris'
                icono = '⚫'
                mensaje = "Sin aprobaciones en 2026"
        else:
            estado = 'gris'
            icono = '⚫'
            mensaje = "Sin meta asignada"
            diff = 0
        
        provincias_data.append({
            'codigo': cod_prov,
            'nombre': NOMBRES_PROVINCIAS.get(cod_prov, cod_prov),
            'monto': round(monto_m, 1),
            'cantidad': cantidad,
            'meta_anual': meta_anual,
            'objetivo_mes': round(objetivo_mes, 1),
            'diferencia': round(diff, 1),
            'estado': estado,
            'icono': icono,
            'mensaje': mensaje
        })
    
    # Ordenar por monto descendente
    provincias_data.sort(key=lambda x: x['monto'], reverse=True)
    
    return provincias_data

def generar_evolucion_mensual(por_mes):
    """Genera datos de evolución mensual"""
    
    meses_nombres = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    
    evolucion = []
    for mes_key in sorted(por_mes.keys()):
        año, mes = mes_key.split('-')
        mes_num = int(mes)
        
        data = por_mes[mes_key]
        monto_m = data['monto'] / 1_000_000
        
        evolucion.append({
            'mes': mes_num,
            'nombre': meses_nombres[mes_num],
            'monto': round(monto_m, 1),
            'cantidad': data['cantidad']
        })
    
    return evolucion

def generar_json(por_provincia, por_mes):
    """Genera el JSON final para el dashboard"""
    
    # Calcular indicadores
    indicadores = calcular_indicadores(por_provincia, por_mes)
    
    # Generar semáforo
    provincias = generar_semaforo_provincias(por_provincia, indicadores['ultimo_mes'])
    
    # Generar evolución mensual
    evolucion = generar_evolucion_mensual(por_mes)
    
    # Estructura final
    datos = {
        'fecha_actualizacion': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total': indicadores,
        'provincias': provincias,
        'evolucion': evolucion
    }
    
    return datos

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 80)
    print("🏦 CFI - PROCESADOR DE DATOS PARA DASHBOARD")
    print("=" * 80)
    
    # Buscar archivo Excel
    archivo = buscar_excel_mas_reciente()
    if not archivo:
        print("\n❌ No se pudo procesar. Verificá que el archivo Excel esté en la carpeta.")
        return
    
    # Procesar Excel
    por_provincia, por_mes = procesar_excel(archivo)
    
    # Generar JSON
    datos = generar_json(por_provincia, por_mes)
    
    # Guardar JSON
    nombre_json = "datos.json"
    with open(nombre_json, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Archivo generado: {nombre_json}")
    print(f"📊 Resumen:")
    print(f"   - Monto total: ${datos['total']['monto']}M")
    print(f"   - Créditos: {datos['total']['creditos']}")
    print(f"   - Progreso: {datos['total']['porcentaje']}%")
    print(f"   - Provincias: {len([p for p in datos['provincias'] if p['cantidad'] > 0])}")
    print(f"   - Meses con datos: {len(datos['evolucion'])}")
    
    print("\n" + "=" * 80)
    print("✓ PROCESO COMPLETADO")
    print("=" * 80)
    print("\n📤 Próximo paso: Subir 'datos.json' a GitHub")
    print("   1. Copiá datos.json al repositorio")
    print("   2. git add datos.json")
    print("   3. git commit -m 'Actualización datos'")
    print("   4. git push")
    print("\n")

if __name__ == "__main__":
    main()
