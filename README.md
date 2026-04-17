# 🏦 CFI - Dashboard Aprobados 2026

Dashboard para visualizar créditos aprobados por el Directorio de CFI en 2026.

**URL del dashboard:** https://ofconde.github.io/dashboard-aprobados/

---

## 📦 ARCHIVOS INCLUIDOS

```
dashboard-aprobados/
├── index.html              ← Dashboard (HTML + CSS + JS)
├── datos.json              ← Datos procesados (generado por script)
├── procesar_excel_cfi.py   ← Script Python para procesar Excel
└── README.md               ← Este archivo
```

---

## 🚀 SETUP INICIAL (Solo una vez)

### 1. Crear el repositorio en GitHub

1. Ir a https://github.com/ofconde
2. Hacer click en **"New repository"** (botón verde)
3. Nombre: `dashboard-aprobados`
4. Descripción: `Dashboard CFI - Créditos Aprobados 2026`
5. ✅ **Public** (importante para GitHub Pages)
6. ✅ Marcar **"Add a README file"**
7. Click en **"Create repository"**

### 2. Activar GitHub Pages

1. Ir a **Settings** (en el repositorio)
2. En el menú izquierdo, click en **Pages**
3. En **Source**, seleccionar **"Deploy from a branch"**
4. En **Branch**, seleccionar **"main"** y carpeta **"/ (root)"**
5. Click en **"Save"**
6. Esperar 1-2 minutos

✅ El dashboard estará disponible en:
```
https://ofconde.github.io/dashboard-aprobados/
```

### 3. Subir los archivos iniciales

**Desde la web de GitHub:**
1. Ir al repositorio en GitHub
2. Click en **"Add file"** → **"Upload files"**
3. Arrastrar los archivos:
   - `index.html`
   - `procesar_excel_cfi.py`
4. Escribir mensaje: `Setup inicial`
5. Click en **"Commit changes"**

---

## 🔄 WORKFLOW DE ACTUALIZACIÓN

### PASO 1: Descargar el Excel del sistema CFI

1. Ir al sistema CFI
2. Descargar el Excel: `CircuitoOtorgamiento-Reporte_export_*.xlsx`
3. Guardarlo en tu carpeta de trabajo (ej: `Downloads\ESTADISTICAS FP\`)

### PASO 2: Procesar el Excel

1. Abrir **terminal** o **cmd** en la carpeta donde está el Excel
2. Ejecutar:
```bash
python procesar_excel_cfi.py
```

3. El script va a:
   - Buscar automáticamente el Excel más reciente
   - Procesar los datos
   - Generar `datos.json`

### PASO 3: Subir datos.json a GitHub

1. Ir al repositorio: https://github.com/ofconde/dashboard-aprobados
2. Si ya existe `datos.json`, hacer click en el archivo y luego en el ícono de lápiz (Edit)
3. Abrir `datos.json` con un editor de texto
4. Copiar TODO el contenido
5. Pegarlo en GitHub
6. Escribir mensaje: `Actualización datos abril 2026`
7. Click en **"Commit changes"**

### PASO 4: Ver el dashboard actualizado

Abrir: https://ofconde.github.io/dashboard-aprobados/

⏱️ Los cambios tardan 1-2 minutos en aparecer.

---

## 📊 QUÉ MUESTRA EL DASHBOARD

### Panel Principal
- **Progreso anual**: Barra de progreso visual
- **Monto aprobado**: Total acumulado 2026
- **Meta anual**: $207.006M
- **Porcentaje**: Avance sobre la meta

### Indicadores
- Total créditos aprobados
- Falta para cumplir meta
- Promedio mensual
- Necesario por mes
- Estado del ritmo (🟢 bien / 🔴 atrasado)

### Semáforo por Provincia
- 🟢 **Verde**: Superó el objetivo (+110%)
- 🟡 **Amarillo**: Cerca del objetivo (90-110%)
- 🔴 **Rojo**: Por debajo del objetivo (<90%)
- ⚫ **Gris**: Sin datos o sin meta

---

## 🔧 REQUISITOS

### Para procesar datos:
- Python 3.7 o superior
- Librería `openpyxl`

**Instalar openpyxl:**
```bash
pip install openpyxl
```

---

## 🆘 SOLUCIÓN DE PROBLEMAS

### "No se encontró ningún archivo con el patrón"
- Verificá que el Excel esté en la misma carpeta que el script
- Verificá que el nombre empiece con `CircuitoOtorgamiento-Reporte_export_`

### "Error al cargar datos.json"
- Verificá que `datos.json` esté en la raíz del repositorio
- Verificá que el archivo tenga contenido válido

### "El dashboard no se actualiza"
- Esperar 1-2 minutos después de hacer push
- Hacer refresh forzado: `Ctrl + F5` (Windows) o `Cmd + Shift + R` (Mac)

---

## 📞 CONTACTO

**Omar Conde**  
CFI - Consejo Federal de Inversiones  
oconde@cfi.org.ar
