# Comparador de financiamiento

- `tasas-datos.json`: condiciones financieras revisadas, metadatos para filtros y snapshots históricos. No incluye CFI.
- `tasas.html`: interfaz y copia inicial de respaldo; se actualiza con `python preparar_tasas.py`.
- `tasas-comparador.js`: filtros, comparación de hasta tres productos, detección de diferencias entre snapshots, vencimientos y pendientes. No convierte tasas variables en tasas fijas ni ordena por una supuesta tasa más barata.
- `tasas-fuentes.json`: fuentes públicas del control automático.
- `monitor_tasas.py`: lectura diaria de HTML y PDF, huellas de bloques relevantes, salud de consulta e historial. No publica texto completo de terceros ni adjudica modificaciones a una tasa sin revisión.
- `monitor-fuentes.json`: resultados y huellas. El navegador lo consulta desde el archivo público del repositorio; los commits hechos con GITHUB_TOKEN no requieren disparar otra publicación de Pages para que el control sea visible.
- Workflow `monitor-tasas.yml`: 11:17 UTC (08:17 Argentina); admite ejecución manual y corre al cambiar el monitor. Los horarios programados de GitHub pueden demorarse.

La tarea de investigación de ChatGPT, a las 09:00 aproximadamente, verifica tasas y novedades y actualiza el JSON financiero y su respaldo HTML. La consulta automática de páginas es independiente de esa tarea; no garantiza que una condición siga vigente ni descubre por sí sola sitios nuevos.

## Datos para filtros

`destino`: Inversión, Capital de trabajo, Leasing o combinación explícita.
`monto_max_ars`, `plazo_max_meses`, `gracia_meses`: números o null. No completar topes por deducción. Cuando depende del tamaño de empresa, null y detalle en condiciones.
`plazos_por_destino`: excepciones por destino (ej. Hacedores: 12 meses capital, 36 inversión).
`tasa_completa`: booleano; requiere porcentaje o fórmula completa con margen publicado. No basta una referencia sin margen.
`vence`: YYYY-MM-DD o null. `fecha_vigencia` y `fecha_anuncio`: fechas explícitas, no fechas de rastreo.

Solo se muestran en Comparar registros con tasa completa, estado Vigencia confirmada, verificación de no más de siete días y sin vencimiento. El resto está en Pendientes. Un filtro numérico excluye límites no publicados y lo aclara en pantalla. Nación y BICE se incluyen como fuentes nacionales, sujetos a elegibilidad.

## Cambios

Se comparan tasa, condiciones, garantías y vigencia entre snapshots sucesivos de la misma línea. Una primera incorporación no se presenta como lanzamiento. Registrar cambios de redacción como tales cuando se modifica una descripción sin cambio comercial. Un `cambio_pendiente` del monitor significa cambio de contenido, no cambio financiero. Tras revisar una fuente se puede guardar `fuentes_revisadas[id] = huella` en el JSON financiero para reconocer esa revisión.

## Verificación y fallos

Las consultas tienen límites de tiempo/tamaño. Un fallo conserva huella y fecha de la última consulta correcta. Recuperar acceso sin nuevas modificaciones conserva el aviso pendiente anterior. La interfaz carga primero el respaldo HTML/JSON y limita cada consulta de red a diez segundos. La revisión financiera no toma la fecha del monitor como fecha de verificación de tasas.

No modificar `datos.json`, la automatización PEI ni sus credenciales para trabajar en este comparador. No agregar datos de solicitantes al repositorio público.
