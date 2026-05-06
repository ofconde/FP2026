(function () {
  const REPORT_PAGE_WIDTH = 1122;
  const REPORT_PAGE_HEIGHT = 794;
  const MM_PER_PX = 0.264583;
  const palette = ['#DDF3FA', '#A7E1EF', '#61C3DC', '#0C8395', '#1C2443'];
  const geoJsonState = { value: null, promise: null };

  function formatMoneyM(value) {
    return new Intl.NumberFormat('es-AR', {
      style: 'currency',
      currency: 'ARS',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format((Number(value || 0)) * 1000000);
  }

  function formatMoneyCompact(value) {
    return `$ ${new Intl.NumberFormat('es-AR', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(Number(value || 0))} M`;
  }

  function formatPercent(value, digits = 1) {
    return `${Number(value || 0).toFixed(digits)}%`;
  }

  function formatCount(value) {
    const count = Number(value || 0);
    return `${count} ${count === 1 ? 'crédito' : 'créditos'}`;
  }

  function normalizeKey(text) {
    return String(text || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_|_$/g, '');
  }

  function monthName(monthNumber) {
    const months = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
    return months[Math.max(0, Number(monthNumber || 1) - 1)] || 'Mes';
  }

  function periodLabel(data) {
    const evolution = (data.evolucion || []).filter((item) => Number(item.cantidad) > 0 || Number(item.monto) > 0);
    const lastMonth = Number(data.total?.ultimo_mes || (evolution[evolution.length - 1] || {}).mes || 1);
    return `Enero / ${monthName(lastMonth)} 2026`;
  }

  function currentDateLabel(data) {
    const value = data.fecha_actualizacion;
    if (!value) return '-';
    const normalized = String(value).replace(' ', 'T');
    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('es-AR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function mercator([lon, lat]) {
    const rad = Math.PI / 180;
    return [lon, Math.log(Math.tan(Math.PI / 4 + (lat * rad) / 2)) / rad];
  }

  function walkCoords(geometry, cb) {
    const visit = (value) => {
      if (typeof value[0] === 'number') cb(value);
      else value.forEach(visit);
    };
    visit(geometry.coordinates);
  }

  function createProjector(features, width, height, pad) {
    const points = [];
    features.forEach((feature) => walkCoords(feature.geometry, (coord) => points.push(mercator(coord))));
    const xs = points.map((point) => point[0]);
    const ys = points.map((point) => point[1]);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const scale = Math.min((width - pad * 2) / (maxX - minX), (height - pad * 2) / (maxY - minY));
    const offsetX = (width - (maxX - minX) * scale) / 2;
    const offsetY = (height - (maxY - minY) * scale) / 2;
    return (coord) => {
      const [x, y] = mercator(coord);
      return [offsetX + (x - minX) * scale, height - (offsetY + (y - minY) * scale)];
    };
  }

  function ringToPath(ring, project) {
    return ring.map((coord, index) => {
      const [x, y] = project(coord);
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ') + ' Z';
  }

  function geometryToPath(geometry, project) {
    if (geometry.type === 'Polygon') {
      return geometry.coordinates.map((ring) => ringToPath(ring, project)).join(' ');
    }
    if (geometry.type === 'MultiPolygon') {
      return geometry.coordinates.flatMap((poly) => poly.map((ring) => ringToPath(ring, project))).join(' ');
    }
    return '';
  }

  function quantile(values, q) {
    if (!values.length) return 0;
    const sorted = [...values].sort((a, b) => a - b);
    const pos = (sorted.length - 1) * q;
    const base = Math.floor(pos);
    const rest = pos - base;
    return sorted[base + 1] !== undefined
      ? sorted[base] + rest * (sorted[base + 1] - sorted[base])
      : sorted[base];
  }

  function buildAmountScale(provincias) {
    const positive = provincias.filter((item) => Number(item.monto) > 0).map((item) => Number(item.monto));
    if (!positive.length) {
      return {
        getColor: () => '#E8EDF1',
        legend: [],
      };
    }
    const q1 = quantile(positive, 0.25);
    const q2 = quantile(positive, 0.5);
    const q3 = quantile(positive, 0.75);
    const max = Math.max(...positive);
    return {
      getColor(value) {
        if (!(value > 0)) return '#E8EDF1';
        if (value >= q3) return value >= max ? palette[4] : palette[3];
        if (value >= q2) return palette[2];
        if (value >= q1) return palette[1];
        return palette[0];
      },
      legend: [
        { color: palette[0], label: `Hasta ${formatMoneyCompact(q1)}` },
        { color: palette[1], label: `${formatMoneyCompact(q1)} a ${formatMoneyCompact(q2)}` },
        { color: palette[2], label: `${formatMoneyCompact(q2)} a ${formatMoneyCompact(q3)}` },
        { color: palette[3], label: `${formatMoneyCompact(q3)} en adelante` },
        { color: palette[4], label: 'Máxima concentración' },
      ],
    };
  }

  async function loadGeoJsonArgentina() {
    if (geoJsonState.value) return geoJsonState.value;
    if (!geoJsonState.promise) {
      geoJsonState.promise = fetch('./mapa_creditos.html', { cache: 'no-store' })
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.text();
        })
        .then((html) => {
          const match = html.match(/<script id="geojsonArgentina" type="application\/json">([\s\S]*?)<\/script>/);
          if (!match) throw new Error('No se pudo leer el mapa base de Argentina.');
          geoJsonState.value = JSON.parse(match[1]);
          return geoJsonState.value;
        });
    }
    return geoJsonState.promise;
  }

  function provinceAliases() {
    return new Map([
      ['buenos_aires', 'Buenos_Aires'],
      ['cordoba', 'Cordoba'],
      ['santa_fe', 'Santa_Fe'],
      ['entre_rios', 'Entre_Rios'],
      ['mendoza', 'Mendoza'],
      ['tucuman', 'Tucuman'],
      ['misiones', 'Misiones'],
      ['rio_negro', 'Rio_Negro'],
      ['salta', 'Salta'],
      ['neuquen', 'Neuquen'],
      ['corrientes', 'Corrientes'],
      ['jujuy', 'Jujuy'],
      ['san_luis', 'San_Luis'],
      ['la_rioja', 'La_Rioja'],
      ['la_pampa', 'La_Pampa'],
      ['chaco', 'Chaco'],
      ['san_juan', 'San_Juan'],
      ['tierra_del_fuego', 'Tierra_del_Fuego'],
      ['chubut', 'Chubut'],
      ['catamarca', 'Catamarca'],
      ['santiago_del_estero', 'Santiago_del_Estero'],
      ['formosa', 'Formosa'],
      ['santa_cruz', 'Santa_Cruz'],
    ]);
  }

  function mapProvinceById(provincias) {
    const aliasMap = provinceAliases();
    const byId = new Map();
    provincias.forEach((provincia) => {
      const key = normalizeKey(provincia.nombre);
      byId.set(aliasMap.get(key) || key, provincia);
    });
    return byId;
  }

  async function buildNationalMapSvg(provincias) {
    const geojson = await loadGeoJsonArgentina();
    const byId = mapProvinceById(provincias);
    const project = createProjector(geojson.features, 520, 420, 18);
    const scale = buildAmountScale(provincias);

    const paths = geojson.features.map((feature) => {
      const geoId = feature.properties.id_mapa || normalizeKey(feature.properties.nombre);
      const provincia = byId.get(geoId);
      const color = scale.getColor(Number(provincia?.monto || 0));
      return `<path d="${geometryToPath(feature.geometry, project)}" fill="${color}" stroke="#FFFFFF" stroke-width="1.4" vector-effect="non-scaling-stroke"></path>`;
    }).join('');

    const legend = scale.legend.map((item) => `
      <div class="report-legend-item">
        <span class="report-legend-color" style="background:${item.color}"></span>
        <span>${item.label}</span>
      </div>
    `).join('');

    return {
      svg: `<svg viewBox="0 0 520 420" class="report-map-svg" xmlns="http://www.w3.org/2000/svg">${paths}</svg>`,
      legend,
    };
  }

  async function buildProvincialMapSvg(provincias, selectedCode) {
    const geojson = await loadGeoJsonArgentina();
    const byId = mapProvinceById(provincias);
    const project = createProjector(geojson.features, 520, 420, 18);

    const selected = provincias.find((item) => item.codigo === selectedCode);
    const paths = geojson.features.map((feature) => {
      const geoId = feature.properties.id_mapa || normalizeKey(feature.properties.nombre);
      const provincia = byId.get(geoId);
      const isSelected = provincia?.codigo === selectedCode;
      const hasData = Number(provincia?.monto || 0) > 0;
      const fill = isSelected ? '#00A7E1' : hasData ? '#CFE7EF' : '#EDF1F4';
      const stroke = isSelected ? '#1C2443' : '#FFFFFF';
      const strokeWidth = isSelected ? '2.2' : '1.2';
      return `<path d="${geometryToPath(feature.geometry, project)}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}" vector-effect="non-scaling-stroke"></path>`;
    }).join('');

    const legend = `
      <div class="report-legend-item">
        <span class="report-legend-color" style="background:#00A7E1"></span>
        <span>${selected ? selected.nombre : 'Provincia seleccionada'}</span>
      </div>
      <div class="report-legend-item">
        <span class="report-legend-color" style="background:#CFE7EF"></span>
        <span>Provincias con actividad en 2026</span>
      </div>
      <div class="report-legend-item">
        <span class="report-legend-color" style="background:#EDF1F4"></span>
        <span>Sin monto aprobado</span>
      </div>
    `;

    return {
      svg: `<svg viewBox="0 0 520 420" class="report-map-svg" xmlns="http://www.w3.org/2000/svg">${paths}</svg>`,
      legend,
    };
  }

  function reportStyles() {
    return `
      <style>
        .report-page {
          width: ${REPORT_PAGE_WIDTH}px;
          height: ${REPORT_PAGE_HEIGHT}px;
          background: linear-gradient(180deg, #F8FBFD 0%, #F4F7FB 100%);
          color: #1C2443;
          font-family: 'Raleway', sans-serif;
          padding: 28px 30px 24px;
          display: flex;
          flex-direction: column;
          gap: 14px;
          overflow: hidden;
          position: relative;
        }
        .report-page::before {
          content: '';
          position: absolute;
          top: -80px;
          right: -60px;
          width: 260px;
          height: 260px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(0,167,225,0.16) 0%, rgba(0,167,225,0) 72%);
        }
        .report-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 18px;
          position: relative;
          z-index: 1;
        }
        .report-kicker {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 1.4px;
          text-transform: uppercase;
          color: #00A7E1;
          margin-bottom: 8px;
        }
        .report-title {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 38px;
          line-height: 0.95;
          letter-spacing: 0.6px;
          margin: 0 0 8px;
        }
        .report-subtitle {
          font-size: 14px;
          color: #5E6A85;
          margin: 0;
        }
        .report-stamp {
          min-width: 200px;
          background: #FFFFFF;
          border: 1px solid #DCE7ED;
          border-radius: 18px;
          padding: 14px 16px;
          box-shadow: 0 10px 26px rgba(28,36,67,0.05);
        }
        .report-stamp-label {
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 1px;
          color: #96C9DA;
          margin-bottom: 6px;
        }
        .report-stamp-value {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 30px;
          line-height: 1;
          color: #1C2443;
        }
        .report-stamp-sub {
          margin-top: 6px;
          font-size: 11px;
          color: #5E6A85;
        }
        .report-hero {
          display: grid;
          grid-template-columns: 1.15fr 1fr;
          gap: 14px;
        }
        .report-goal-card, .report-note-card, .report-block, .report-kpi-card {
          background: rgba(255,255,255,0.95);
          border: 1px solid #DCE7ED;
          border-radius: 18px;
          box-shadow: 0 12px 28px rgba(28,36,67,0.05);
        }
        .report-goal-card {
          padding: 18px 20px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          min-height: 120px;
        }
        .report-goal-label {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 1px;
          color: #96C9DA;
          margin-bottom: 10px;
        }
        .report-goal-value {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 46px;
          line-height: 0.95;
          color: #1C2443;
        }
        .report-goal-sub {
          margin-top: 10px;
          font-size: 12px;
          color: #5E6A85;
        }
        .report-note-card {
          padding: 18px 20px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          background: linear-gradient(135deg, #00A7E1 0%, #0C8395 100%);
          color: white;
        }
        .report-note-label {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 1px;
          text-transform: uppercase;
          opacity: 0.78;
          margin-bottom: 10px;
        }
        .report-note-text {
          font-size: 14px;
          line-height: 1.55;
        }
        .report-kpi-grid {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 12px;
        }
        .report-kpi-card {
          padding: 14px 16px;
        }
        .report-kpi-label {
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 1px;
          text-transform: uppercase;
          color: #96C9DA;
          margin-bottom: 8px;
        }
        .report-kpi-value {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 28px;
          line-height: 1;
          color: #1C2443;
          margin-bottom: 6px;
        }
        .report-kpi-sub {
          font-size: 11px;
          color: #5E6A85;
          line-height: 1.35;
        }
        .report-main {
          display: grid;
          grid-template-columns: 1.15fr 0.85fr;
          gap: 14px;
          min-height: 0;
          flex: 1;
        }
        .report-block {
          padding: 16px 18px;
          min-height: 0;
          display: flex;
          flex-direction: column;
        }
        .report-block-title {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 22px;
          letter-spacing: 0.5px;
          margin: 0 0 4px;
        }
        .report-block-subtitle {
          font-size: 11px;
          color: #5E6A85;
          margin: 0 0 12px;
          line-height: 1.45;
        }
        .report-map-shell {
          flex: 1;
          display: grid;
          grid-template-columns: 1fr 168px;
          gap: 12px;
          min-height: 0;
        }
        .report-map-stage {
          background: linear-gradient(180deg, #F8FBFD 0%, #EFF6FA 100%);
          border: 1px solid #E0ECF2;
          border-radius: 16px;
          padding: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .report-map-svg {
          width: 100%;
          height: auto;
          max-height: 290px;
          display: block;
        }
        .report-legend {
          display: grid;
          gap: 10px;
          align-content: start;
        }
        .report-legend-item {
          display: flex;
          gap: 8px;
          align-items: center;
          font-size: 11px;
          color: #42506D;
          line-height: 1.35;
        }
        .report-legend-color {
          width: 14px;
          height: 14px;
          border-radius: 4px;
          border: 1px solid rgba(28,36,67,0.1);
          flex: 0 0 auto;
        }
        .report-side-stack {
          display: grid;
          gap: 12px;
          min-height: 0;
        }
        .report-progress-track {
          height: 14px;
          border-radius: 999px;
          background: #E5EEF2;
          overflow: hidden;
          margin: 12px 0 10px;
        }
        .report-progress-fill {
          height: 100%;
          border-radius: 999px;
          background: linear-gradient(90deg, #00A7E1 0%, #0C8395 100%);
        }
        .report-progress-meta {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          font-size: 11px;
          color: #5E6A85;
        }
        .report-rank-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 10px 0;
          border-top: 1px solid #ECF2F5;
        }
        .report-rank-row:first-child { border-top: 0; }
        .report-rank-name {
          font-size: 12px;
          font-weight: 700;
          color: #1C2443;
          text-transform: uppercase;
        }
        .report-rank-meta {
          font-size: 10px;
          color: #5E6A85;
          margin-top: 2px;
        }
        .report-rank-value {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 24px;
          line-height: 1;
          color: #1C2443;
          white-space: nowrap;
        }
        .report-participation-list {
          display: grid;
          gap: 10px;
        }
        .report-participation-row {
          display: grid;
          grid-template-columns: 92px 1fr auto;
          gap: 10px;
          align-items: center;
        }
        .report-participation-name {
          font-size: 11px;
          font-weight: 700;
          color: #1C2443;
          text-transform: uppercase;
        }
        .report-participation-bar {
          height: 10px;
          border-radius: 999px;
          background: #EAF1F4;
          overflow: hidden;
        }
        .report-participation-fill {
          height: 100%;
          border-radius: 999px;
          background: linear-gradient(90deg, #00A7E1 0%, #0C8395 100%);
        }
        .report-participation-value {
          font-size: 11px;
          font-weight: 700;
          color: #1C2443;
          white-space: nowrap;
        }
        .report-footer {
          display: flex;
          justify-content: space-between;
          gap: 14px;
          align-items: center;
          font-size: 10px;
          color: #7A869F;
        }
        .report-footer-brand {
          font-weight: 700;
          letter-spacing: 1px;
          text-transform: uppercase;
          color: #96C9DA;
        }
        .report-page.compact {
          padding: 22px 24px 18px;
          gap: 10px;
        }
        .report-page.compact .report-title {
          font-size: 34px;
        }
        .report-page.compact .report-subtitle,
        .report-page.compact .report-note-text,
        .report-page.compact .report-goal-sub,
        .report-page.compact .report-block-subtitle {
          font-size: 12px;
          line-height: 1.4;
        }
        .report-page.compact .report-goal-value {
          font-size: 40px;
        }
        .report-page.compact .report-stamp-value {
          font-size: 26px;
        }
        .report-page.compact .report-kpi-grid {
          gap: 10px;
        }
        .report-page.compact .report-kpi-card,
        .report-page.compact .report-block,
        .report-page.compact .report-goal-card,
        .report-page.compact .report-note-card {
          padding: 14px 16px;
        }
        .report-page.compact .report-kpi-value {
          font-size: 24px;
        }
        .report-page.compact .report-main,
        .report-page.compact .report-hero,
        .report-page.compact .report-map-shell,
        .report-page.compact .report-side-stack {
          gap: 10px;
        }
        .report-page.compact .report-map-svg {
          max-height: 250px;
        }
        .report-page.compact .report-rank-row {
          padding: 7px 0;
        }
        .report-page.compact .report-rank-name,
        .report-page.compact .report-participation-name {
          font-size: 11px;
        }
        .report-page.compact .report-rank-value {
          font-size: 20px;
        }
        .report-page.compact .report-footer,
        .report-page.compact .report-legend-item,
        .report-page.compact .report-progress-meta,
        .report-page.compact .report-rank-meta,
        .report-page.compact .report-participation-value {
          font-size: 10px;
        }
        .report-page.compact-tight {
          padding: 18px 20px 14px;
          gap: 8px;
        }
        .report-page.compact-tight .report-title {
          font-size: 30px;
        }
        .report-page.compact-tight .report-goal-value {
          font-size: 34px;
        }
        .report-page.compact-tight .report-stamp-value,
        .report-page.compact-tight .report-kpi-value,
        .report-page.compact-tight .report-rank-value {
          font-size: 20px;
        }
        .report-page.compact-tight .report-kpi-card,
        .report-page.compact-tight .report-block,
        .report-page.compact-tight .report-goal-card,
        .report-page.compact-tight .report-note-card {
          padding: 12px 14px;
        }
        .report-page.compact-tight .report-map-svg {
          max-height: 220px;
        }
        .report-page.compact-tight .report-rank-row {
          padding: 5px 0;
        }
      </style>
    `;
  }

  function buildKpiCard(label, value, sub) {
    return `
      <div class="report-kpi-card">
        <div class="report-kpi-label">${label}</div>
        <div class="report-kpi-value">${value}</div>
        <div class="report-kpi-sub">${sub}</div>
      </div>
    `;
  }

  async function renderProvincialReport(data, provinceCode) {
    const provincia = (data.provincias || []).find((item) => item.codigo === provinceCode);
    const detail = (data.detalles || []).find((item) => item.codigo === provinceCode) || provincia;
    if (!provincia || !detail) {
      throw new Error('No se encontró la provincia seleccionada en los datos disponibles.');
    }
    if (!(Number(provincia.meta_anual) > 0)) {
      throw new Error(`No se puede generar el informe porque falta el objetivo provincial de ${provincia.nombre}.`);
    }

    const provinciasOrdenadas = [...(data.provincias || [])].sort((a, b) => Number(b.monto || 0) - Number(a.monto || 0));
    const rank = provinciasOrdenadas.findIndex((item) => item.codigo === provinceCode) + 1;
    const participation = data.total?.monto ? (Number(provincia.monto) / Number(data.total.monto)) * 100 : 0;
    const avgTicket = provincia.cantidad ? Number(provincia.monto) / Number(provincia.cantidad) : 0;
    const progress = provincia.meta_anual ? (Number(provincia.monto) / Number(provincia.meta_anual)) * 100 : 0;
    const map = await buildProvincialMapSvg(data.provincias || [], provinceCode);

    const note = `${provincia.nombre} representa el ${formatPercent(participation)} del total nacional otorgado durante el período informado y ocupa el puesto ${rank} dentro del ranking nacional por monto.`;

    return `
      ${reportStyles()}
      <div class="report-page provincial-report">
        <div class="report-header">
          <div>
            <div class="report-kicker">Consejo Federal de Inversiones</div>
            <h1 class="report-title">Informe de Créditos CFI — ${provincia.nombre}</h1>
            <p class="report-subtitle">${periodLabel(data)} · Actualizado al ${currentDateLabel(data)}</p>
          </div>
          <div class="report-stamp">
            <div class="report-stamp-label">RANKING NACIONAL</div>
            <div class="report-stamp-value">#${rank}</div>
            <div class="report-stamp-sub">según monto otorgado acumulado</div>
          </div>
        </div>

        <div class="report-hero">
          <div class="report-goal-card">
            <div class="report-goal-label">OBJETIVO PROVINCIAL 2026</div>
            <div class="report-goal-value">${formatMoneyCompact(provincia.meta_anual)}</div>
            <div class="report-goal-sub">Equivale a ${formatMoneyM(provincia.meta_anual)} como meta anual asignada.</div>
          </div>
          <div class="report-note-card">
            <div class="report-note-label">LECTURA EJECUTIVA</div>
            <div class="report-note-text">${note}</div>
          </div>
        </div>

        <div class="report-kpi-grid">
          ${buildKpiCard('Otorgado', formatMoneyCompact(provincia.monto), formatCount(provincia.cantidad))}
          ${buildKpiCard('Participación nacional', formatPercent(participation), 'Sobre el monto total país')}
          ${buildKpiCard('Avance objetivo', formatPercent(progress), `Brecha: ${formatMoneyCompact(Math.abs(Number(provincia.diferencia || 0)))}`)}
          ${buildKpiCard('Promedio por crédito', formatMoneyCompact(avgTicket), formatMoneyM(avgTicket))}
          ${buildKpiCard('Estado actual', formatPercent(provincia.porcentaje), provincia.mensaje || 'Seguimiento de meta')}
        </div>

        <div class="report-main">
          <div class="report-block">
            <h2 class="report-block-title">Mapa Federal</h2>
            <p class="report-block-subtitle">La provincia analizada se resalta sobre el resto del mapa para ubicar rápidamente su peso territorial dentro del sistema.</p>
            <div class="report-map-shell">
              <div class="report-map-stage">${map.svg}</div>
              <div class="report-legend">${map.legend}</div>
            </div>
          </div>

          <div class="report-side-stack">
            <div class="report-block">
              <h2 class="report-block-title">Avance contra objetivo</h2>
              <p class="report-block-subtitle">Comparación directa entre monto aprobado acumulado y la meta provincial 2026.</p>
              <div class="report-progress-track">
                <div class="report-progress-fill" style="width:${Math.min(progress, 100)}%"></div>
              </div>
              <div class="report-progress-meta">
                <span>Otorgado: ${formatMoneyCompact(provincia.monto)}</span>
                <span>Meta: ${formatMoneyCompact(provincia.meta_anual)}</span>
              </div>
            </div>

            <div class="report-block">
              <h2 class="report-block-title">Top provincias</h2>
              <p class="report-block-subtitle">Contexto nacional para leer la posición relativa de ${provincia.nombre}.</p>
              ${provinciasOrdenadas.slice(0, 5).map((item, index) => `
                <div class="report-rank-row">
                  <div>
                    <div class="report-rank-name">#${index + 1} · ${item.nombre}</div>
                    <div class="report-rank-meta">${formatCount(item.cantidad)} · ${formatPercent(data.total?.monto ? (Number(item.monto) / Number(data.total.monto)) * 100 : 0)} del total</div>
                  </div>
                  <div class="report-rank-value">${formatMoneyCompact(item.monto)}</div>
                </div>
              `).join('')}
            </div>
          </div>
        </div>

        <div class="report-footer">
          <div class="report-footer-brand">CFI · Financiamiento Productivo · Uso institucional</div>
          <div>Generado automáticamente desde el dashboard 2026</div>
        </div>
      </div>
    `;
  }

  async function renderNationalReport(data) {
    const provincias = data.provincias || [];
    const active = provincias.filter((item) => Number(item.monto) > 0);
    const provinciasOrdenadas = [...active].sort((a, b) => Number(b.monto || 0) - Number(a.monto || 0));
    const map = await buildNationalMapSvg(provincias);
    const avgNational = data.total?.creditos ? Number(data.total.monto) / Number(data.total.creditos) : 0;
    const topThree = provinciasOrdenadas.slice(0, 3);
    const topShare = topThree.reduce((acc, item) => acc + (data.total?.monto ? (Number(item.monto) / Number(data.total.monto)) * 100 : 0), 0);
    const note = `El sistema acumula ${formatMoneyCompact(data.total?.monto || 0)} en ${data.total?.creditos || 0} créditos, con ${active.length} provincias alcanzadas. Las tres jurisdicciones líderes concentran ${formatPercent(topShare)} del volumen nacional informado.`;

    return `
      ${reportStyles()}
      <div class="report-page national-report">
        <div class="report-header">
          <div>
            <div class="report-kicker">Consejo Federal de Inversiones</div>
            <h1 class="report-title">Informe Nacional de Créditos CFI</h1>
            <p class="report-subtitle">${periodLabel(data)} · Actualizado al ${currentDateLabel(data)}</p>
          </div>
          <div class="report-stamp">
            <div class="report-stamp-label">AVANCE GENERAL</div>
            <div class="report-stamp-value">${formatPercent(data.total?.porcentaje || 0)}</div>
            <div class="report-stamp-sub">sobre el objetivo nacional 2026</div>
          </div>
        </div>

        <div class="report-hero">
          <div class="report-goal-card">
            <div class="report-goal-label">OBJETIVO NACIONAL 2026</div>
            <div class="report-goal-value">${formatMoneyCompact(data.total?.meta || 0)}</div>
            <div class="report-goal-sub">Monto faltante para cumplir: ${formatMoneyCompact(data.total?.falta || 0)}</div>
          </div>
          <div class="report-note-card">
            <div class="report-note-label">LECTURA EJECUTIVA</div>
            <div class="report-note-text">${note}</div>
          </div>
        </div>

        <div class="report-kpi-grid">
          ${buildKpiCard('Monto nacional', formatMoneyCompact(data.total?.monto || 0), formatMoneyM(data.total?.monto || 0))}
          ${buildKpiCard('Créditos', `${data.total?.creditos || 0}`, formatCount(data.total?.creditos || 0))}
          ${buildKpiCard('Provincias alcanzadas', `${active.length}`, 'Con aprobaciones en el período')}
          ${buildKpiCard('Promedio nacional', formatMoneyCompact(avgNational), 'Monto medio por crédito')}
          ${buildKpiCard('Necesario por mes', formatMoneyCompact(data.total?.necesario_por_mes || 0), `${data.total?.meses_restantes || 0} meses restantes`)}
        </div>

        <div class="report-main">
          <div class="report-block">
            <h2 class="report-block-title">Mapa coroplético</h2>
            <p class="report-block-subtitle">Las provincias se colorean según monto otorgado acumulado, usando la misma lógica territorial del dashboard interactivo.</p>
            <div class="report-map-shell">
              <div class="report-map-stage">${map.svg}</div>
              <div class="report-legend">${map.legend}</div>
            </div>
          </div>

          <div class="report-side-stack">
            <div class="report-block">
              <h2 class="report-block-title">Ranking por monto</h2>
              <p class="report-block-subtitle">Principales jurisdicciones por volumen otorgado en el período.</p>
              ${provinciasOrdenadas.slice(0, 5).map((item, index) => `
                <div class="report-rank-row">
                  <div>
                    <div class="report-rank-name">#${index + 1} · ${item.nombre}</div>
                    <div class="report-rank-meta">${formatCount(item.cantidad)} · ${formatPercent(item.porcentaje)} de avance</div>
                  </div>
                  <div class="report-rank-value">${formatMoneyCompact(item.monto)}</div>
                </div>
              `).join('')}
            </div>

            <div class="report-block">
              <h2 class="report-block-title">Participación principal</h2>
              <p class="report-block-subtitle">Peso relativo de las provincias líderes sobre el total nacional informado.</p>
              <div class="report-participation-list">
                ${topThree.map((item) => {
                  const share = data.total?.monto ? (Number(item.monto) / Number(data.total.monto)) * 100 : 0;
                  return `
                    <div class="report-participation-row">
                      <div class="report-participation-name">${item.codigo}</div>
                      <div class="report-participation-bar"><div class="report-participation-fill" style="width:${Math.min(share, 100)}%"></div></div>
                      <div class="report-participation-value">${formatPercent(share)}</div>
                    </div>
                  `;
                }).join('')}
              </div>
            </div>
          </div>
        </div>

        <div class="report-footer">
          <div class="report-footer-brand">CFI · Financiamiento Productivo · Uso institucional</div>
          <div>Generado automáticamente desde el dashboard 2026</div>
        </div>
      </div>
    `;
  }

  async function ensurePdfLibrary() {
    if (window.html2pdf) return window.html2pdf;
    throw new Error('La librería de exportación PDF no está disponible en este momento.');
  }

  async function exportReport({ filename, html, mountNode }) {
    const html2pdf = await ensurePdfLibrary();
    const previousStyle = mountNode.getAttribute('style') || '';
    mountNode.setAttribute('style', 'position:fixed;left:0;top:0;width:1122px;pointer-events:none;z-index:1;overflow:visible;');
    mountNode.innerHTML = html;
    const page = mountNode.querySelector('.report-page');
    if (!page) {
      mountNode.innerHTML = '';
      mountNode.setAttribute('style', previousStyle);
      throw new Error('No se pudo construir la hoja del informe para exportar.');
    }

    await new Promise((resolve) => setTimeout(resolve, 180));
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
    }

    const fitReport = async () => {
      const overflowHeight = () => page.scrollHeight > REPORT_PAGE_HEIGHT;
      const overflowWidth = () => page.scrollWidth > REPORT_PAGE_WIDTH;

      if (overflowHeight() || overflowWidth()) {
        page.classList.add('compact');
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
      if (overflowHeight() || overflowWidth()) {
        page.classList.add('compact-tight');
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
    };

    await fitReport();

    const rect = page.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      mountNode.innerHTML = '';
      mountNode.setAttribute('style', previousStyle);
      throw new Error('No se pudo calcular el tamaño del informe para exportar.');
    }

    const options = {
      margin: 0,
      filename,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: {
        scale: 2,
        useCORS: true,
        backgroundColor: '#F4F7FB',
        logging: false,
      },
      jsPDF: {
        unit: 'mm',
        format: 'a4',
        orientation: 'landscape',
      },
      pagebreak: { mode: ['avoid-all'] },
    };
    await html2pdf().set(options).from(page).save();
    mountNode.innerHTML = '';
    mountNode.setAttribute('style', previousStyle);
  }

  async function generateProvincialReport({ data, provinceCode, mountNode }) {
    const html = await renderProvincialReport(data, provinceCode);
    const provincia = (data.provincias || []).find((item) => item.codigo === provinceCode);
    const filename = `informe_creditos_${normalizeKey(provincia?.nombre || provinceCode)}_2026.pdf`;
    return exportReport({ filename, html, mountNode });
  }

  async function generateNationalReport({ data, mountNode }) {
    const html = await renderNationalReport(data);
    return exportReport({ filename: 'informe_nacional_creditos_cfi_2026.pdf', html, mountNode });
  }

  window.CFIReports = {
    generateProvincialReport,
    generateNationalReport,
  };
})();
