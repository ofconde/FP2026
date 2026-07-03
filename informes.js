(function () {
  const REPORT_PAGE_WIDTH = 1122;
  const REPORT_PAGE_HEIGHT = 794;
  const REPORT_PAGE_WIDTH_P = 816;
  const REPORT_PAGE_HEIGHT_P = 1056;
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

  function geometryBounds(geometry) {
    const points = [];
    walkCoords(geometry, (coord) => points.push(mercator(coord)));
    const xs = points.map((point) => point[0]);
    const ys = points.map((point) => point[1]);
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }

  function expandBounds(bounds, targetWidth, targetHeight) {
    const centerX = (bounds.minX + bounds.maxX) / 2;
    const centerY = (bounds.minY + bounds.maxY) / 2;
    return {
      minX: centerX - targetWidth / 2,
      maxX: centerX + targetWidth / 2,
      minY: centerY - targetHeight / 2,
      maxY: centerY + targetHeight / 2,
    };
  }

  function createProjectorFromBounds(bounds, width, height, pad) {
    const spanX = Math.max(bounds.maxX - bounds.minX, 0.0001);
    const spanY = Math.max(bounds.maxY - bounds.minY, 0.0001);
    const scale = Math.min((width - pad * 2) / spanX, (height - pad * 2) / spanY);
    const offsetX = (width - spanX * scale) / 2;
    const offsetY = (height - spanY * scale) / 2;
    return (coord) => {
      const [x, y] = mercator(coord);
      return [offsetX + (x - bounds.minX) * scale, height - (offsetY + (y - bounds.minY) * scale)];
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
    const selected = provincias.find((item) => item.codigo === selectedCode);
    const selectedFeature = geojson.features.find((feature) => {
      const geoId = feature.properties.id_mapa || normalizeKey(feature.properties.nombre);
      const provincia = byId.get(geoId);
      return provincia?.codigo === selectedCode;
    });
    const nationalProject = createProjector(geojson.features, 132, 186, 10);
    const countryBounds = geometryBounds({
      type: 'MultiPolygon',
      coordinates: geojson.features.flatMap((feature) => (
        feature.geometry.type === 'MultiPolygon'
          ? feature.geometry.coordinates
          : [feature.geometry.coordinates]
      )),
    });
    const selectedBounds = selectedFeature ? geometryBounds(selectedFeature.geometry) : countryBounds;
    const selectedWidth = Math.max(selectedBounds.maxX - selectedBounds.minX, 0.8);
    const selectedHeight = Math.max(selectedBounds.maxY - selectedBounds.minY, 0.8);
    const focusBounds = expandBounds(
      selectedBounds,
      Math.max(selectedWidth * 3.4, (countryBounds.maxX - countryBounds.minX) * 0.2),
      Math.max(selectedHeight * 2.9, (countryBounds.maxY - countryBounds.minY) * 0.24),
    );
    const focusProject = createProjectorFromBounds(focusBounds, 332, 344, 14);

    const focusPaths = geojson.features.map((feature) => {
      const geoId = feature.properties.id_mapa || normalizeKey(feature.properties.nombre);
      const provincia = byId.get(geoId);
      const isSelected = provincia?.codigo === selectedCode;
      const path = geometryToPath(feature.geometry, focusProject);
      if (!path) return '';
      if (isSelected) {
        return `
          <path d="${path}" fill="none" stroke="rgba(28,36,67,0.16)" stroke-width="10" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"></path>
          <path d="${path}" fill="#10B7E8" stroke="#1C2443" stroke-width="2.8" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"></path>
        `;
      }
      return `<path d="${path}" fill="#E9F2F6" stroke="#FFFFFF" stroke-width="1.3" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"></path>`;
    }).join('');

    const insetPaths = geojson.features.map((feature) => {
      const geoId = feature.properties.id_mapa || normalizeKey(feature.properties.nombre);
      const provincia = byId.get(geoId);
      const isSelected = provincia?.codigo === selectedCode;
      return `<path d="${geometryToPath(feature.geometry, nationalProject)}" fill="${isSelected ? '#1C2443' : '#D6EAF2'}" stroke="${isSelected ? '#FFFFFF' : '#FFFFFF'}" stroke-width="${isSelected ? '1.8' : '0.9'}" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"></path>`;
    }).join('');

    const mapLabel = selected ? `
      <g transform="translate(358 264)">
        <text x="0" y="0" font-family="Raleway, sans-serif" font-size="11" font-weight="800" fill="#1C2443">${selected.nombre.toUpperCase()}</text>
        <text x="0" y="18" font-family="Raleway, sans-serif" font-size="10" fill="#5E6A85">foco territorial del informe provincial</text>
      </g>
    ` : '';

    const legend = `
      <div class="report-legend-item">
        <span class="report-legend-color" style="background:#10B7E8"></span>
        <span>${selected ? selected.nombre : 'Provincia analizada'}</span>
      </div>
      <div class="report-legend-item">
        <span class="report-legend-color" style="background:#D6EAF2"></span>
        <span>Localizador nacional</span>
      </div>
      <div class="report-legend-item">
        <span class="report-legend-color" style="background:#E9F2F6"></span>
        <span>Entorno territorial de referencia</span>
      </div>
    `;

    return {
      svg: `
        <svg viewBox="0 0 520 420" class="report-map-svg report-map-svg-provincial" xmlns="http://www.w3.org/2000/svg">
          <rect x="8" y="10" width="344" height="368" rx="20" fill="url(#provincialBg)" stroke="#DCE9F0"></rect>
          <rect x="364" y="18" width="148" height="196" rx="18" fill="#F8FBFD" stroke="#DCE9F0"></rect>
          <defs>
            <linearGradient id="provincialBg" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stop-color="#F9FCFE"></stop>
              <stop offset="100%" stop-color="#EDF5FA"></stop>
            </linearGradient>
          </defs>
          <g transform="translate(18 22)">${focusPaths}</g>
          <g transform="translate(372 24)">
            <text x="0" y="10" font-family="Raleway, sans-serif" font-size="10" font-weight="800" letter-spacing="1" fill="#96C9DA">POSICIÓN NACIONAL</text>
            <g transform="translate(2 18)">${insetPaths}</g>
          </g>
          ${mapLabel}
        </svg>
      `,
      legend,
    };
  }

  function reportStyles() {
    return `
      <style>
        .report-page {
          width: ${REPORT_PAGE_WIDTH}px;
          min-height: ${REPORT_PAGE_HEIGHT}px;
          background: linear-gradient(180deg, #F8FBFD 0%, #F4F7FB 100%);
          color: #1C2443;
          font-family: 'Raleway', sans-serif;
          padding: 28px 30px 24px;
          display: flex;
          flex-direction: column;
          gap: 14px;
          position: relative;
        }
        .provincial-report {
          height: ${REPORT_PAGE_HEIGHT}px;
          overflow: hidden;
        }
        .national-report {
          height: auto;
          overflow: visible;
          padding-bottom: 30px;
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
        .report-map-svg-provincial {
          max-height: 328px;
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
        .national-report .report-main {
          flex: 0 0 auto;
          min-height: auto;
          align-items: start;
        }
        .national-report .report-block,
        .national-report .report-goal-card,
        .national-report .report-note-card,
        .national-report .report-kpi-card,
        .national-report .report-rank-row,
        .national-report .report-participation-row,
        .national-report .report-footer {
          break-inside: avoid;
          page-break-inside: avoid;
        }
        .national-report .report-map-shell,
        .national-report .report-side-stack,
        .national-report .report-kpi-grid,
        .national-report .report-hero {
          break-inside: avoid;
          page-break-inside: avoid;
        }
        .national-report + .national-report {
          margin-top: 18px;
        }
        .national-report-secondary::before {
          opacity: 0.65;
        }
        .national-two-col {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 14px;
        }
        .national-stat-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 12px;
        }
        .national-stat-card {
          background: rgba(255,255,255,0.95);
          border: 1px solid #DCE7ED;
          border-radius: 18px;
          box-shadow: 0 12px 28px rgba(28,36,67,0.05);
          padding: 14px 16px;
        }
        .national-stat-label {
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 1px;
          text-transform: uppercase;
          color: #96C9DA;
          margin-bottom: 8px;
        }
        .national-stat-value {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 24px;
          line-height: 1;
          color: #1C2443;
          margin-bottom: 6px;
        }
        .national-stat-sub {
          font-size: 11px;
          color: #5E6A85;
          line-height: 1.35;
        }
        .report-table-lite {
          width: 100%;
          border-collapse: collapse;
          font-size: 11px;
        }
        .report-table-lite th,
        .report-table-lite td {
          padding: 9px 0;
          border-top: 1px solid #ECF2F5;
          text-align: left;
          vertical-align: top;
        }
        .report-table-lite th {
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 0.8px;
          text-transform: uppercase;
          color: #96C9DA;
          border-top: 0;
          padding-top: 0;
        }
        .report-table-lite td:last-child,
        .report-table-lite th:last-child {
          text-align: right;
        }
        .report-table-lite td:nth-child(2),
        .report-table-lite th:nth-child(2) {
          text-align: center;
        }
        .report-chip-row {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
        }
        .report-chip {
          background: #F2F7FA;
          border: 1px solid #DCE7ED;
          border-radius: 999px;
          padding: 8px 12px;
          font-size: 11px;
          color: #42506D;
        }
        .report-chip strong {
          color: #1C2443;
        }
        .report-bullet-list {
          display: grid;
          gap: 10px;
        }
        .report-bullet-item {
          background: #F6FAFC;
          border: 1px solid #E0ECF2;
          border-radius: 14px;
          padding: 12px 14px;
        }
        .report-bullet-title {
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 0.9px;
          text-transform: uppercase;
          color: #96C9DA;
          margin-bottom: 6px;
        }
        .report-bullet-text {
          font-size: 12px;
          line-height: 1.45;
          color: #1C2443;
        }
        .report-month-grid {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 10px;
          align-items: end;
        }
        .report-month-card {
          background: #F8FBFD;
          border: 1px solid #E0ECF2;
          border-radius: 14px;
          padding: 12px 10px;
          display: grid;
          gap: 8px;
        }
        .report-month-name {
          font-size: 11px;
          font-weight: 800;
          color: #1C2443;
          text-transform: uppercase;
        }
        .report-month-bar {
          height: 10px;
          background: #EAF1F4;
          border-radius: 999px;
          overflow: hidden;
        }
        .report-month-fill {
          height: 100%;
          border-radius: 999px;
          background: linear-gradient(90deg, #00A7E1 0%, #0C8395 100%);
        }
        .report-month-value {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 22px;
          color: #1C2443;
          line-height: 1;
        }
        .report-month-sub {
          font-size: 10px;
          color: #5E6A85;
        }
        .report-warning-grid {
          display: grid;
          gap: 10px;
        }
        .report-warning-row {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 10px;
          align-items: center;
          padding: 10px 0;
          border-top: 1px solid #ECF2F5;
        }
        .report-warning-row:first-child {
          border-top: 0;
          padding-top: 0;
        }
        .report-warning-name {
          font-size: 12px;
          font-weight: 800;
          color: #1C2443;
          text-transform: uppercase;
        }
        .report-warning-meta {
          font-size: 10px;
          color: #5E6A85;
          margin-top: 3px;
        }
        .report-warning-value {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 22px;
          color: #E6431A;
          white-space: nowrap;
        }
        .report-section-divider {
          height: 1px;
          background: linear-gradient(90deg, rgba(150,201,218,0) 0%, rgba(150,201,218,0.8) 50%, rgba(150,201,218,0) 100%);
          margin: 4px 0;
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
        .report-page.compact .report-map-svg-provincial {
          max-height: 286px;
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
        .report-page.compact-tight .report-map-svg-provincial {
          max-height: 252px;
        }
        .report-page.compact-tight .report-rank-row {
          padding: 5px 0;
        }
        .report-identity {
          align-items: center;
          justify-content: center;
          gap: 12px;
          text-align: center;
        }
        .report-identity-ring {
          position: relative;
          width: 130px;
          height: 130px;
          flex-shrink: 0;
        }
        .report-identity-ring svg {
          width: 130px;
          height: 130px;
          display: block;
        }
        .report-identity-ring-pct {
          position: absolute;
          inset: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
        }
        .report-identity-ring-value {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 36px;
          line-height: 1;
          color: #1C2443;
        }
        .report-identity-ring-label {
          font-size: 9px;
          font-weight: 700;
          letter-spacing: 1px;
          color: #96C9DA;
          text-transform: uppercase;
        }
        .report-identity-name {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 40px;
          line-height: 0.95;
          color: #1C2443;
          letter-spacing: 0.5px;
        }
        .report-identity-monto {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 24px;
          color: #00A7E1;
          line-height: 1;
        }
        .report-identity-monto-label {
          font-size: 10px;
          color: #5E6A85;
          margin-top: 2px;
        }
        .report-identity-stats {
          display: flex;
          gap: 18px;
          justify-content: center;
          padding: 10px 0;
          border-top: 1px solid #ECF2F5;
          border-bottom: 1px solid #ECF2F5;
          width: 100%;
        }
        .report-identity-stat-val {
          font-size: 17px;
          font-weight: 700;
          color: #1C2443;
        }
        .report-identity-stat-label {
          font-size: 9px;
          color: #5E6A85;
          text-transform: uppercase;
          letter-spacing: 0.8px;
        }
        .report-identity-stat-div {
          width: 1px;
          background: #ECF2F5;
          align-self: stretch;
        }
        .report-identity-badge {
          display: inline-block;
          padding: 4px 14px;
          border-radius: 999px;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.8px;
          text-transform: uppercase;
        }
        .report-identity-badge.verde { background: #e7f7ef; color: #1a7a45; }
        .report-identity-badge.amarillo { background: #fef3e2; color: #8a5700; }
        .report-identity-badge.rojo { background: #fde8e8; color: #9e2222; }
        .report-identity-cuatri {
          width: 100%;
          background: #F8FBFD;
          border: 1px solid #E0ECF2;
          border-radius: 12px;
          padding: 10px 14px;
          text-align: left;
        }
        .report-identity-cuatri-label {
          font-size: 9px;
          font-weight: 700;
          letter-spacing: 1px;
          color: #96C9DA;
          text-transform: uppercase;
          margin-bottom: 4px;
        }
        .report-identity-cuatri-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
        }
        .report-identity-cuatri-pct {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 22px;
          color: #1C2443;
        }
        @media print {
          .print-shell.multi-page .report-page {
            break-after: page;
            page-break-after: always;
          }
          .print-shell.multi-page .report-page:last-child {
            break-after: auto;
            page-break-after: auto;
          }
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

  function buildPortraitDocument({ title, reportHtml }) {
    const W = REPORT_PAGE_WIDTH_P;
    const H = REPORT_PAGE_HEIGHT_P;
    return `<!doctype html>
      <html lang="es">
        <head>
          <meta charset="utf-8">
          <title>${title}</title>
          <link rel="preconnect" href="https://fonts.googleapis.com">
          <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
          <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Raleway:wght@400;500;600;700;800&display=swap" rel="stylesheet">
          <style>
            @page { size: Letter portrait; margin: 0; }
            html, body { margin: 0; padding: 0; background: #e8ecf0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            body { font-family: 'Raleway', sans-serif; }
            .print-shell { width: ${W}px; min-height: ${H}px; margin: 0 auto; }
            @media screen { body { padding: 18px; } .print-shell { box-shadow: 0 20px 40px rgba(28,36,67,0.14); } }
            @media print { body { padding: 0; background: white; } .print-shell { box-shadow: none; width: ${W}px; height: ${H}px; overflow: hidden; } }
          </style>
        </head>
        <body>
          <div class="print-shell">${reportHtml}</div>
          <script>
            (async () => {
              if (document.fonts && document.fonts.ready) try { await document.fonts.ready; } catch(e) {}
              await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
              window.print();
            })();
          <\/script>
        </body>
      </html>`;
  }

  async function renderProvincialReport(data, provinceCode) {
    const provincia = (data.provincias || []).find((item) => item.codigo === provinceCode);
    const detail = (data.detalles || []).find((item) => item.codigo === provinceCode) || provincia;
    if (!provincia || !detail) throw new Error('No se encontró la provincia seleccionada en los datos disponibles.');
    if (!(Number(provincia.meta_anual) > 0)) throw new Error(`No se puede generar el informe porque falta el objetivo provincial de ${provincia.nombre}.`);

    const provinciasOrdenadas = [...(data.provincias || [])].sort((a, b) => Number(b.monto || 0) - Number(a.monto || 0));
    const rank = provinciasOrdenadas.findIndex((item) => item.codigo === provinceCode) + 1;
    const participation = data.total?.monto ? (Number(provincia.monto) / Number(data.total.monto)) * 100 : 0;
    const avgTicket = provincia.cantidad ? Number(provincia.monto) / Number(provincia.cantidad) : 0;
    const progress = Math.min((Number(provincia.monto) / Number(provincia.meta_anual)) * 100, 100);
    const cuatriProgress = Math.min(Number(detail.porcentaje_cuatrimestral || 0), 100);

    const ringColors = { verde: '#47B067', amarillo: '#E5A020', rojo: '#D84040' };
    const ringAnualColor = ringColors[provincia.estado] || '#00A7E1';
    const ringCuatriColor = ringColors[detail.estado_cuatrimestral] || '#D84040';

    const RO = 86; const RI = 66;
    const circO = 2 * Math.PI * RO; const circI = 2 * Math.PI * RI;
    const offO = circO * (1 - progress / 100);
    const offI = circI * (1 - cuatriProgress / 100);

    const escudoExt = provinceCode === 'SL' ? 'png' : 'svg';
    const escudoSrc = `./escudos/${provinceCode}.${escudoExt}`;

    const evolucionProv = {};
    (detail.items || []).forEach((item) => {
      if (!item.fecha_resolucion) return;
      const mes = parseInt(item.fecha_resolucion.split('-')[1], 10);
      evolucionProv[mes] = (evolucionProv[mes] || 0) + Number(item.importe || 0);
    });
    const mesesConDatos = Object.keys(evolucionProv).map(Number).sort((a, b) => a - b);
    const maxEvol = Math.max(...Object.values(evolucionProv), 1);
    const nombresCortos = ['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
    const ultimoMes = mesesConDatos[mesesConDatos.length - 1] || 0;
    const BAR_H = 80;

    const topMax = Number(provinciasOrdenadas[0]?.monto || 1);
    const topRows = provinciasOrdenadas.slice(0, 5).map((item, i) => {
      const isMe = item.codigo === provinceCode;
      const w = Math.round((Number(item.monto) / topMax) * 100);
      return `<div class="rp-rank-row${isMe ? ' rp-rank-me' : ''}">
        <div class="rp-rank-pos">#${i + 1}</div>
        <div class="rp-rank-name">${item.nombre}</div>
        <div class="rp-rank-bar-wrap"><div class="rp-rank-fill${isMe ? ' rp-rank-fill-me' : ''}" style="width:${w}%"></div></div>
        <div class="rp-rank-val">${formatMoneyCompact(item.monto)}</div>
      </div>`;
    }).join('');

    const badgeColors = {
      verde: 'background:#e7f7ef;color:#1a7a45',
      amarillo: 'background:#fef3e2;color:#8a5700',
      rojo: 'background:#fde8e8;color:#9e2222',
    };
    const badgeAnual = badgeColors[provincia.estado] || badgeColors.verde;
    const badgeCuatri = badgeColors[detail.estado_cuatrimestral] || badgeColors.rojo;

    return `
      <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        .rp { width: ${REPORT_PAGE_WIDTH_P}px; min-height: ${REPORT_PAGE_HEIGHT_P}px; background: #f8fbfd; color: #1C2443; font-family: 'Raleway', sans-serif; display: flex; flex-direction: column; }
        .rp-hdr { background: #1C2443; padding: 14px 28px; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
        .rp-hdr-kicker { font-size: 9px; font-weight: 700; letter-spacing: 2px; color: #00A7E1; text-transform: uppercase; margin-bottom: 3px; }
        .rp-hdr-title { font-size: 13px; font-weight: 700; color: #fff; }
        .rp-hdr-right { font-size: 10px; color: #96C9DA; text-align: right; line-height: 1.5; }
        .rp-hero { display: flex; align-items: center; gap: 18px; padding: 16px 28px; border-bottom: 1px solid #e0ecf2; flex-shrink: 0; background: #fff; }
        .rp-escudo { width: 64px; height: 74px; object-fit: contain; flex-shrink: 0; }
        .rp-prov-info { flex: 1; }
        .rp-prov-name { font-family: 'Bebas Neue', sans-serif; font-size: 42px; line-height: 1; color: #1C2443; letter-spacing: 0.5px; }
        .rp-prov-sub { font-size: 11px; color: #5E6A85; margin-top: 3px; }
        .rp-badge { display: inline-block; margin-top: 7px; font-size: 9px; font-weight: 700; padding: 4px 12px; border-radius: 20px; letter-spacing: 0.8px; text-transform: uppercase; }
        .rp-rank-box { text-align: center; padding: 12px 18px; border-left: 1px solid #e0ecf2; flex-shrink: 0; }
        .rp-rank-box-label { font-size: 9px; font-weight: 700; letter-spacing: 1.2px; color: #96C9DA; text-transform: uppercase; margin-bottom: 4px; }
        .rp-rank-box-val { font-family: 'Bebas Neue', sans-serif; font-size: 44px; color: #1C2443; line-height: 1; }
        .rp-rank-box-sub { font-size: 10px; color: #5E6A85; margin-top: 2px; }
        .rp-ring-section { display: flex; align-items: center; gap: 28px; padding: 18px 28px; border-bottom: 1px solid #e0ecf2; flex-shrink: 0; background: #f8fbfd; }
        .rp-ring-wrap { position: relative; width: 200px; height: 200px; flex-shrink: 0; }
        .rp-ring-wrap svg { width: 200px; height: 200px; }
        .rp-ring-inner { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1px; }
        .rp-ring-pct { font-family: 'Bebas Neue', sans-serif; font-size: 46px; line-height: 1; color: #1C2443; }
        .rp-ring-sub { font-size: 9px; font-weight: 700; letter-spacing: 1px; color: #96C9DA; text-transform: uppercase; }
        .rp-ring-sep { width: 32px; height: 1px; background: #e0ecf2; margin: 3px 0; }
        .rp-ring-cpct { font-family: 'Bebas Neue', sans-serif; font-size: 28px; line-height: 1; color: #5E6A85; }
        .rp-ring-csub { font-size: 9px; color: #96C9DA; letter-spacing: 0.8px; }
        .rp-ring-info { flex: 1; display: flex; flex-direction: column; gap: 12px; }
        .rp-ring-monto { font-family: 'Bebas Neue', sans-serif; font-size: 34px; color: #00A7E1; line-height: 1; }
        .rp-ring-monto-label { font-size: 11px; color: #5E6A85; margin-top: 2px; }
        .rp-ring-legend { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
        .rp-ring-legend-item { display: flex; align-items: center; gap: 8px; font-size: 11px; color: #42506D; }
        .rp-ring-legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
        .rp-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 14px 28px; flex-shrink: 0; }
        .rp-kpi { background: #fff; border: 1px solid #e0ecf2; border-radius: 10px; padding: 12px 14px; }
        .rp-kpi-val { font-family: 'Bebas Neue', sans-serif; font-size: 24px; color: #1C2443; line-height: 1; }
        .rp-kpi-label { font-size: 9px; font-weight: 700; letter-spacing: 1px; color: #96C9DA; text-transform: uppercase; margin-top: 4px; }
        .rp-objs { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 0 28px 14px; flex-shrink: 0; }
        .rp-obj { background: #fff; border: 1px solid #e0ecf2; border-radius: 10px; padding: 14px 16px; }
        .rp-obj-label { font-size: 9px; font-weight: 700; letter-spacing: 1.2px; color: #96C9DA; text-transform: uppercase; margin-bottom: 6px; }
        .rp-obj-meta { font-size: 11px; font-weight: 700; color: #1C2443; margin-bottom: 8px; }
        .rp-obj-track { height: 10px; background: #E5EEF2; border-radius: 5px; overflow: hidden; margin-bottom: 8px; }
        .rp-obj-fill { height: 100%; border-radius: 5px; }
        .rp-obj-row { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
        .rp-obj-pct { font-family: 'Bebas Neue', sans-serif; font-size: 26px; line-height: 1; }
        .rp-obj-brecha { font-size: 10px; color: #5E6A85; }
        .rp-evol { padding: 0 28px 14px; flex-shrink: 0; }
        .rp-sec-label { font-size: 9px; font-weight: 700; letter-spacing: 1.5px; color: #96C9DA; text-transform: uppercase; margin-bottom: 10px; }
        .rp-bars { display: flex; align-items: flex-end; gap: 8px; height: ${BAR_H}px; }
        .rp-bar-col { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 5px; height: 100%; justify-content: flex-end; }
        .rp-bar { width: 100%; border-radius: 3px 3px 0 0; min-height: 3px; }
        .rp-bar.past { background: #b8d8e8; }
        .rp-bar.cur { background: #00A7E1; }
        .rp-bar-lbl { font-size: 9px; color: #96C9DA; }
        .rp-axis { height: 1px; background: #e0ecf2; margin: 0 28px 14px; }
        .rp-ranking { padding: 0 28px; flex: 1; }
        .rp-rank-row { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-top: 1px solid #f0f4f7; }
        .rp-rank-row:first-child { border-top: 0; }
        .rp-rank-me { background: #f0f8ff; margin: 0 -8px; padding: 7px 8px; border-radius: 6px; border-top: 0 !important; }
        .rp-rank-pos { font-size: 10px; font-weight: 700; color: #96C9DA; width: 22px; flex-shrink: 0; }
        .rp-rank-name { font-size: 11px; font-weight: 700; color: #1C2443; width: 130px; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .rp-rank-me .rp-rank-name { color: #00A7E1; }
        .rp-rank-bar-wrap { flex: 1; height: 8px; background: #eef3f6; border-radius: 4px; overflow: hidden; }
        .rp-rank-fill { height: 100%; border-radius: 4px; background: #1C2443; }
        .rp-rank-fill-me { background: #00A7E1; }
        .rp-rank-val { font-size: 11px; font-weight: 700; color: #1C2443; white-space: nowrap; width: 80px; text-align: right; flex-shrink: 0; }
        .rp-rank-me .rp-rank-val { color: #00A7E1; }
        .rp-footer { background: #1C2443; padding: 10px 28px; display: flex; justify-content: space-between; align-items: center; margin-top: auto; flex-shrink: 0; }
        .rp-footer-brand { font-size: 9px; font-weight: 700; letter-spacing: 1.5px; color: #96C9DA; text-transform: uppercase; }
        .rp-footer-page { font-size: 9px; color: #4a5a7a; }
      </style>
      <div class="rp">
        <div class="rp-hdr">
          <div>
            <div class="rp-hdr-kicker">Consejo Federal de Inversiones</div>
            <div class="rp-hdr-title">Informe Provincial · Financiamiento Productivo 2026</div>
          </div>
          <div class="rp-hdr-right">${periodLabel(data)}<br>Actualizado ${currentDateLabel(data)}</div>
        </div>

        <div class="rp-hero">
          <img class="rp-escudo" src="${escudoSrc}" alt="Escudo de ${provincia.nombre}" onerror="this.style.visibility='hidden'">
          <div class="rp-prov-info">
            <div class="rp-prov-name">${provincia.nombre}</div>
            <div class="rp-prov-sub">Financiamiento Productivo · ${periodLabel(data)}</div>
            <span class="rp-badge" style="${badgeAnual}">${provincia.mensaje || 'En seguimiento'}</span>
          </div>
          <div class="rp-rank-box">
            <div class="rp-rank-box-label">Ranking nacional</div>
            <div class="rp-rank-box-val">#${rank}</div>
            <div class="rp-rank-box-sub">por monto aprobado</div>
          </div>
        </div>

        <div class="rp-ring-section">
          <div class="rp-ring-wrap">
            <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
              <circle cx="100" cy="100" r="${RO}" fill="none" stroke="#E5EEF2" stroke-width="16"/>
              <circle cx="100" cy="100" r="${RO}" fill="none" stroke="${ringAnualColor}" stroke-width="16"
                stroke-dasharray="${circO.toFixed(2)}" stroke-dashoffset="${offO.toFixed(2)}"
                stroke-linecap="round" transform="rotate(-90 100 100)"/>
              <circle cx="100" cy="100" r="${RI}" fill="none" stroke="#E5EEF2" stroke-width="11"/>
              <circle cx="100" cy="100" r="${RI}" fill="none" stroke="${ringCuatriColor}" stroke-width="11"
                stroke-dasharray="${circI.toFixed(2)}" stroke-dashoffset="${offI.toFixed(2)}"
                stroke-linecap="round" transform="rotate(-90 100 100)"/>
            </svg>
            <div class="rp-ring-inner">
              <div class="rp-ring-pct">${Math.round(progress)}%</div>
              <div class="rp-ring-sub">Obj. anual</div>
              <div class="rp-ring-sep"></div>
              <div class="rp-ring-cpct">${Math.round(cuatriProgress)}%</div>
              <div class="rp-ring-csub">cuatrimestral</div>
            </div>
          </div>
          <div class="rp-ring-info">
            <div>
              <div class="rp-ring-monto">${formatMoneyCompact(provincia.monto)}</div>
              <div class="rp-ring-monto-label">aprobado · ${periodLabel(data)}</div>
            </div>
            <div class="rp-ring-legend">
              <div class="rp-ring-legend-item">
                <div class="rp-ring-legend-dot" style="background:${ringAnualColor}"></div>
                <span>Cumplimiento anual — ${formatPercent(progress)} del objetivo</span>
              </div>
              <div class="rp-ring-legend-item">
                <div class="rp-ring-legend-dot" style="background:${ringCuatriColor}"></div>
                <span>Cuatrimestre JUL–OCT — ${formatPercent(cuatriProgress)}</span>
                <span class="rp-badge" style="${badgeCuatri};font-size:8px;padding:2px 8px;margin-left:4px;">${detail.mensaje_cuatrimestral || ''}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="rp-kpis">
          <div class="rp-kpi"><div class="rp-kpi-val">${provincia.cantidad || 0}</div><div class="rp-kpi-label">Créditos aprobados</div></div>
          <div class="rp-kpi"><div class="rp-kpi-val">${formatMoneyCompact(avgTicket)}</div><div class="rp-kpi-label">Promedio por crédito</div></div>
          <div class="rp-kpi"><div class="rp-kpi-val">${formatPercent(participation)}</div><div class="rp-kpi-label">Participación nacional</div></div>
          <div class="rp-kpi"><div class="rp-kpi-val">${formatMoneyCompact(Math.abs(Number(provincia.diferencia || 0)))}</div><div class="rp-kpi-label">Brecha al objetivo</div></div>
        </div>

        <div class="rp-objs">
          <div class="rp-obj">
            <div class="rp-obj-label">Objetivo anual 2026</div>
            <div class="rp-obj-meta">Meta: ${formatMoneyCompact(provincia.meta_anual)}</div>
            <div class="rp-obj-track"><div class="rp-obj-fill" style="width:${progress}%;background:${ringAnualColor}"></div></div>
            <div class="rp-obj-row">
              <div class="rp-obj-pct" style="color:${ringAnualColor}">${Math.round(progress)}%</div>
              <div class="rp-obj-brecha">Brecha: ${formatMoneyCompact(Math.abs(Number(provincia.diferencia || 0)))}</div>
            </div>
          </div>
          <div class="rp-obj">
            <div class="rp-obj-label">Objetivo cuatrimestral JUL–OCT</div>
            <div class="rp-obj-meta">Meta: ${formatMoneyCompact(detail.meta_cuatrimestral || 0)}</div>
            <div class="rp-obj-track"><div class="rp-obj-fill" style="width:${cuatriProgress}%;background:${ringCuatriColor}"></div></div>
            <div class="rp-obj-row">
              <div class="rp-obj-pct" style="color:${ringCuatriColor}">${Math.round(cuatriProgress)}%</div>
              <span class="rp-badge" style="${badgeCuatri};font-size:9px;padding:3px 10px;">${detail.mensaje_cuatrimestral || 'Sin inicio'}</span>
            </div>
          </div>
        </div>

        ${mesesConDatos.length > 0 ? `
        <div class="rp-evol">
          <div class="rp-sec-label">Evolución mensual — monto aprobado en ${provincia.nombre}</div>
          <div class="rp-bars">
            ${mesesConDatos.map((mes) => {
              const monto = evolucionProv[mes] || 0;
              const h = Math.max(Math.round((monto / maxEvol) * BAR_H), 3);
              const isCur = mes === ultimoMes;
              return `<div class="rp-bar-col">
                <div class="rp-bar ${isCur ? 'cur' : 'past'}" style="height:${h}px"></div>
                <div class="rp-bar-lbl" style="${isCur ? 'color:#00A7E1;font-weight:700' : ''}">${nombresCortos[mes]}</div>
              </div>`;
            }).join('')}
          </div>
        </div>
        <div class="rp-axis"></div>
        ` : ''}

        <div class="rp-ranking">
          <div class="rp-sec-label">Ranking nacional por monto aprobado</div>
          ${topRows}
        </div>

        <div class="rp-footer">
          <div class="rp-footer-brand">CFI · Financiamiento Productivo · Uso institucional</div>
          <div class="rp-footer-page">1 de 1</div>
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
    const topByCredits = [...active].sort((a, b) => Number(b.cantidad || 0) - Number(a.cantidad || 0)).slice(0, 6);
    const topByAmount = provinciasOrdenadas.slice(0, 6);
    const topShare = topThree.reduce((acc, item) => acc + (data.total?.monto ? (Number(item.monto) / Number(data.total.monto)) * 100 : 0), 0);
    const totalActiveMeta = active.reduce((acc, item) => acc + Number(item.meta_anual || 0), 0);
    const greenCount = active.filter((item) => Number(item.porcentaje || 0) >= 80).length;
    const yellowCount = active.filter((item) => Number(item.porcentaje || 0) >= 50 && Number(item.porcentaje || 0) < 80).length;
    const redCount = active.filter((item) => Number(item.porcentaje || 0) < 50).length;
    const medianProvince = provinciasOrdenadas[Math.floor(Math.max(provinciasOrdenadas.length - 1, 0) / 2)] || null;
    const avgPerProvince = active.length ? Number(data.total?.monto || 0) / active.length : 0;
    const topBottom = [...active].sort((a, b) => Number(a.porcentaje || 0) - Number(b.porcentaje || 0)).slice(0, 5);
    const monthly = (data.evolucion || []).filter((item) => Number(item.monto || 0) > 0 || Number(item.cantidad || 0) > 0);
    const maxMonthly = Math.max(...monthly.map((item) => Number(item.monto || 0)), 1);
    const topProvince = provinciasOrdenadas[0] || null;
    const secondProvince = provinciasOrdenadas[1] || null;
    const note = `El sistema acumula ${formatMoneyCompact(data.total?.monto || 0)} en ${data.total?.creditos || 0} créditos, con ${active.length} provincias alcanzadas. Las tres jurisdicciones líderes concentran ${formatPercent(topShare)} del volumen nacional informado.`;
    const strategicNotes = [
      {
        title: 'Concentración',
        text: topProvince ? `${topProvince.nombre} lidera con ${formatMoneyCompact(topProvince.monto)} y explica ${formatPercent(data.total?.monto ? (Number(topProvince.monto) / Number(data.total.monto)) * 100 : 0)} del total nacional.` : 'Sin datos de liderazgo disponibles.',
      },
      {
        title: 'Capilaridad',
        text: `${active.length} provincias ya registran aprobaciones. El promedio operativo por provincia activa es ${formatMoneyCompact(avgPerProvince)}.`,
      },
      {
        title: 'Ritmo',
        text: data.total?.ritmo_ok ? `El ritmo promedio (${formatMoneyCompact(data.total?.promedio_mensual || 0)} por mes) se mantiene alineado con la necesidad proyectada.` : `El ritmo promedio (${formatMoneyCompact(data.total?.promedio_mensual || 0)} por mes) todavía queda por debajo de lo necesario (${formatMoneyCompact(data.total?.necesario_por_mes || 0)} por mes).`,
      },
    ];

    return `
      ${reportStyles()}
      <div class="report-page national-report national-report-page national-report-primary">
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
            <h2 class="report-block-title">Mapa federal y cobertura</h2>
            <p class="report-block-subtitle">Distribución territorial del monto aprobado acumulado para ver concentración, alcance federal y escala relativa entre jurisdicciones.</p>
            <div class="report-map-shell">
              <div class="report-map-stage">${map.svg}</div>
              <div class="report-legend">${map.legend}</div>
            </div>
          </div>

          <div class="report-side-stack">
            <div class="report-block">
              <h2 class="report-block-title">Claves para decisión</h2>
              <p class="report-block-subtitle">Tres señales que una autoridad nacional querría leer primero: concentración, capilaridad y ritmo.</p>
              <div class="report-bullet-list">
                ${strategicNotes.map((item) => `
                  <div class="report-bullet-item">
                    <div class="report-bullet-title">${item.title}</div>
                    <div class="report-bullet-text">${item.text}</div>
                  </div>
                `).join('')}
              </div>
            </div>

            <div class="report-block">
              <h2 class="report-block-title">Evolución mensual</h2>
              <p class="report-block-subtitle">Ritmo del monto aprobado mes a mes, para identificar aceleración, amesetamiento o necesidad de corrección.</p>
              <div class="report-month-grid">
                ${monthly.map((item) => `
                  <div class="report-month-card">
                    <div class="report-month-name">${item.nombre}</div>
                    <div class="report-month-bar"><div class="report-month-fill" style="width:${Math.max(8, (Number(item.monto || 0) / maxMonthly) * 100)}%"></div></div>
                    <div class="report-month-value">${formatMoneyCompact(item.monto || 0)}</div>
                    <div class="report-month-sub">${item.cantidad || 0} créditos</div>
                  </div>
                `).join('')}
              </div>
            </div>

            <div class="report-block">
              <h2 class="report-block-title">Semáforo territorial</h2>
              <p class="report-block-subtitle">Lectura agregada del avance provincial sobre metas anuales, útil para priorizar asistencia y seguimiento.</p>
              <div class="report-chip-row">
                <div class="report-chip"><strong>Verdes:</strong> ${greenCount}</div>
                <div class="report-chip"><strong>Amarillas:</strong> ${yellowCount}</div>
                <div class="report-chip"><strong>Rojas:</strong> ${redCount}</div>
                <div class="report-chip"><strong>Top 2:</strong> ${topProvince ? topProvince.codigo : '-'}${secondProvince ? ` + ${secondProvince.codigo}` : ''}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="report-footer">
          <div class="report-footer-brand">CFI · Financiamiento Productivo · Uso institucional</div>
          <div>Página 1 de 2 · Foto nacional y contexto</div>
        </div>
      </div>

      <div class="report-page national-report national-report-page national-report-secondary">
        <div class="report-header">
          <div>
            <div class="report-kicker">Consejo Federal de Inversiones</div>
            <h1 class="report-title">Apertura territorial y focos de gestión</h1>
            <p class="report-subtitle">Desglose de liderazgo, concentración y rezagos provinciales sobre el mismo corte de información.</p>
          </div>
          <div class="report-stamp">
            <div class="report-stamp-label">CONCENTRACIÓN TOP 3</div>
            <div class="report-stamp-value">${formatPercent(topShare)}</div>
            <div class="report-stamp-sub">del volumen nacional acumulado</div>
          </div>
        </div>

        <div class="national-stat-grid">
          <div class="national-stat-card">
            <div class="national-stat-label">Promedio por provincia activa</div>
            <div class="national-stat-value">${formatMoneyCompact(avgPerProvince)}</div>
            <div class="national-stat-sub">${active.length} provincias con aprobaciones</div>
          </div>
          <div class="national-stat-card">
            <div class="national-stat-label">Meta agregada activa</div>
            <div class="national-stat-value">${formatMoneyCompact(totalActiveMeta)}</div>
            <div class="national-stat-sub">Suma de metas provinciales con actividad</div>
          </div>
          <div class="national-stat-card">
            <div class="national-stat-label">Provincia mediana</div>
            <div class="national-stat-value">${medianProvince ? medianProvince.codigo : '-'}</div>
            <div class="national-stat-sub">${medianProvince ? formatMoneyCompact(medianProvince.monto) : 'Sin datos suficientes'}</div>
          </div>
          <div class="national-stat-card">
            <div class="national-stat-label">Cobertura operativa</div>
            <div class="national-stat-value">${formatPercent((active.length / Math.max(provincias.length, 1)) * 100)}</div>
            <div class="national-stat-sub">${active.length} de ${provincias.length} provincias con monto</div>
          </div>
        </div>

        <div class="national-two-col">
          <div class="report-block">
            <h2 class="report-block-title">Ranking por monto</h2>
            <p class="report-block-subtitle">Jurisdicciones con mayor volumen aprobado, combinando monto, cantidad y avance relativo.</p>
            ${topByAmount.map((item, index) => `
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
            <p class="report-block-subtitle">Peso relativo de las provincias líderes sobre el total nacional, para leer concentración de cartera.</p>
            <div class="report-participation-list">
              ${provinciasOrdenadas.slice(0, 5).map((item) => {
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

        <div class="report-section-divider"></div>

        <div class="national-two-col">
          <div class="report-block">
            <h2 class="report-block-title">Mayor volumen operativo</h2>
            <p class="report-block-subtitle">Provincias con más créditos aprobados, para ver dónde el instrumento está logrando mayor despliegue y capilaridad.</p>
            ${topByCredits.map((item, index) => `
              <div class="report-rank-row">
                <div>
                  <div class="report-rank-name">#${index + 1} · ${item.nombre}</div>
                  <div class="report-rank-meta">${formatMoneyCompact(item.monto)} · ${formatPercent(data.total?.monto ? (Number(item.monto) / Number(data.total.monto)) * 100 : 0)} del total</div>
                </div>
                <div class="report-rank-value">${item.cantidad}</div>
              </div>
            `).join('')}
          </div>

          <div class="report-block">
            <h2 class="report-block-title">Focos de gestión</h2>
            <p class="report-block-subtitle">Provincias con menor nivel de avance y mayor necesidad de seguimiento sobre el tramo restante del año.</p>
            <div class="report-warning-grid">
              ${topBottom.map((item) => `
                <div class="report-warning-row">
                  <div>
                    <div class="report-warning-name">${item.nombre}</div>
                    <div class="report-warning-meta">${formatMoneyCompact(item.monto)} otorgados · brecha ${formatMoneyCompact(Math.abs(Number(item.diferencia || 0)))}</div>
                  </div>
                  <div class="report-warning-value">${formatPercent(item.porcentaje)}</div>
                </div>
              `).join('')}
            </div>
          </div>
        </div>

        <div class="report-footer">
          <div class="report-footer-brand">CFI · Financiamiento Productivo · Uso institucional</div>
          <div>Página 2 de 2 · Apertura nacional</div>
        </div>
      </div>
    `;
  }

  function buildPrintDocument({ title, reportHtml }) {
    return `<!doctype html>
      <html lang="es">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>${title}</title>
          <link rel="preconnect" href="https://fonts.googleapis.com">
          <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
          <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Raleway:wght@400;500;600;700;800&display=swap" rel="stylesheet">
          <style>
            @page {
              size: A4 landscape;
              margin: 0;
            }
            html, body {
              margin: 0;
              padding: 0;
              background: #E9EEF2;
              -webkit-print-color-adjust: exact;
              print-color-adjust: exact;
            }
            body {
              font-family: 'Raleway', sans-serif;
            }
            .print-shell {
              width: ${REPORT_PAGE_WIDTH}px;
              min-height: ${REPORT_PAGE_HEIGHT}px;
              margin: 0 auto;
            }
            @media screen {
              body {
                padding: 18px;
              }
              .print-shell {
                box-shadow: 0 20px 40px rgba(28,36,67,0.14);
              }
            }
            @media print {
              body {
                padding: 0;
                background: white;
              }
              .print-shell {
                box-shadow: none;
                width: ${REPORT_PAGE_WIDTH}px;
              }
              .print-shell.single-page {
                height: ${REPORT_PAGE_HEIGHT}px;
                overflow: hidden;
              }
              .print-shell.single-page .provincial-report {
                transform: scale(0.94);
                transform-origin: top left;
                width: 1194px;
                min-height: 845px;
              }
              .print-shell.single-page .provincial-report .report-map-svg {
                max-height: 235px;
              }
              .print-shell.single-page .provincial-report .report-kpi-card,
              .print-shell.single-page .provincial-report .report-block,
              .print-shell.single-page .provincial-report .report-goal-card,
              .print-shell.single-page .provincial-report .report-note-card {
                padding: 12px 14px;
              }
              .print-shell.single-page .provincial-report .report-main,
              .print-shell.single-page .provincial-report .report-hero,
              .print-shell.single-page .provincial-report .report-map-shell,
              .print-shell.single-page .provincial-report .report-side-stack,
              .print-shell.single-page .provincial-report .report-kpi-grid {
                gap: 10px;
              }
              .print-shell.multi-page {
                min-height: auto;
                height: auto;
                overflow: visible;
              }
            }
          </style>
        </head>
        <body>
          <div class="print-shell">${reportHtml}</div>
          <script>
            const waitForReady = async () => {
              if (document.fonts && document.fonts.ready) {
                try { await document.fonts.ready; } catch (e) {}
              }
              await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
              const shell = document.querySelector('.print-shell');
              const page = document.querySelector('.report-page');
              if (!page || !shell) return;

              const isProvincial = page.classList.contains('provincial-report');
              shell.classList.add(isProvincial ? 'single-page' : 'multi-page');

              if (!isProvincial) {
                page.style.height = 'auto';
                page.style.minHeight = '${REPORT_PAGE_HEIGHT}px';
                page.style.overflow = 'visible';
                window.print();
                return;
              }

              const targetWidth = ${REPORT_PAGE_WIDTH};
              const targetHeight = ${REPORT_PAGE_HEIGHT};
              const overflowHeight = () => page.scrollHeight > targetHeight;
              const overflowWidth = () => page.scrollWidth > targetWidth;

              if (overflowHeight() || overflowWidth()) {
                page.classList.add('compact');
                await new Promise((resolve) => requestAnimationFrame(resolve));
              }
              if (overflowHeight() || overflowWidth()) {
                page.classList.add('compact-tight');
                await new Promise((resolve) => requestAnimationFrame(resolve));
              }

              const visualWidth = Math.max(page.scrollWidth, page.offsetWidth, targetWidth);
              const visualHeight = Math.max(page.scrollHeight, page.offsetHeight, targetHeight);
              const scale = Math.min(targetWidth / visualWidth, targetHeight / visualHeight, 1);
              if (scale < 0.999) {
                page.style.transformOrigin = 'top left';
                page.style.transform = 'scale(' + scale + ')';
              }
              window.print();
            };
            waitForReady();
          <\/script>
        </body>
      </html>`;
  }

  async function generateProvincialReport({ data, provinceCode }) {
    const html = await renderProvincialReport(data, provinceCode);
    const provincia = (data.provincias || []).find((item) => item.codigo === provinceCode);
    const reportTitle = `Dashboard CFI - Financiamiento Productivo 2026 - ${provincia?.nombre || provinceCode}`;
    return {
      title: reportTitle,
      documentHtml: buildPortraitDocument({
        title: reportTitle,
        reportHtml: html,
      }),
    };
  }

  async function generateNationalReport({ data }) {
    const html = await renderNationalReport(data);
    const reportTitle = 'Dashboard CFI - Financiamiento Productivo 2026 - Nacional';
    return {
      title: reportTitle,
      documentHtml: buildPrintDocument({
        title: reportTitle,
        reportHtml: html,
      }),
    };
  }

  window.CFIReports = {
    generateProvincialReport,
    generateNationalReport,
  };
})();
