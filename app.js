// app.js — логика карты, фильтров и режима хронологии

const MIN_YEAR = 1991;
const MAX_YEAR = 2026;

// ---------- Данные ----------
// allIncidents = статические данные (data.js) + удары БПЛА, подгружаемые
// асинхронно из drone-strikes.json и периодически обновляемые.
let allIncidents = [...incidents];

// ---------- Состояние ----------
const state = {
  selectedRegions: new Set(allIncidents.map(i => i.region)),
  selectedTypes: new Set(Object.keys(INCIDENT_TYPES)),
  yearFrom: MIN_YEAR,
  yearTo: MAX_YEAR,
  chronoYear: MAX_YEAR,
  onlyCurrentYear: false,
  playing: false,
  playTimer: null,
};

// ---------- Карта ----------
const map = L.map('map', { worldCopyJump: true }).setView([61, 90], 3);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 18,
}).addTo(map);

// Leaflet рисует в своей атрибуции (низ-справа) маленький флаг рядом со
// ссылкой на leafletjs.com — по умолчанию сине-жёлтый, с полосами разной
// высоты (4:3:1 из 8), поэтому просто перекрасить через CSS не получится
// сделать равными третями — меняем сами фигуры на три честные равные трети
// бело-сине-красного цвета.
function fixAttributionFlag() {
  const svg = document.querySelector('.leaflet-attribution-flag');
  if (!svg) return;
  const third = 8 / 3;
  svg.innerHTML = `
    <rect x="0" y="0" width="12" height="${third}" fill="#ffffff"></rect>
    <rect x="0" y="${third}" width="12" height="${third}" fill="#0039a6"></rect>
    <rect x="0" y="${third * 2}" width="12" height="${8 - third * 2}" fill="#d52b1e"></rect>
  `;
}
fixAttributionFlag();

const markersLayer = L.layerGroup().addTo(map);
const markerById = {};

function makeIcon(type, highlighted) {
  const color = INCIDENT_TYPES[type]?.color || '#999';
  const isAggregate = type === 'drone_intercept_night';
  // Агрегатные ночные маркеры делаем мельче и полупрозрачными без белой
  // окантовки — их на порядок больше, и они не должны визуально спорить
  // с точечными инцидентами.
  const size = highlighted ? (isAggregate ? 14 : 22) : (isAggregate ? 8 : 16);
  const border = isAggregate ? '1px solid rgba(255,255,255,0.45)' : '2px solid rgba(255,255,255,0.85)';
  const opacity = isAggregate ? 0.55 : 1;
  return L.divIcon({
    className: '',
    html: `<div style="
      width:${size}px;height:${size}px;border-radius:50%;
      background:${color};border:${border};opacity:${opacity};
      box-shadow:0 0 4px rgba(0,0,0,0.5);
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

// ---------- Построение списков фильтров ----------
const regionListEl = document.getElementById('regionList');
let uniqueRegions = [...new Set(allIncidents.map(i => i.region))].sort((a, b) => a.localeCompare(b, 'ru'));

function addRegionCheckbox(region) {
  const label = document.createElement('label');
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = true;
  cb.dataset.region = region;
  cb.addEventListener('change', () => {
    if (cb.checked) state.selectedRegions.add(region);
    else state.selectedRegions.delete(region);
    render();
  });
  label.appendChild(cb);
  label.appendChild(document.createTextNode(region));
  regionListEl.appendChild(label);
}

uniqueRegions.forEach(addRegionCheckbox);

// Вызывается после подгрузки новых данных (например, ударов БПЛА), чтобы
// добавить чекбоксы для регионов, которых не было в исходном наборе.
function rebuildRegionList() {
  const currentRegions = [...new Set(allIncidents.map(i => i.region))].sort((a, b) => a.localeCompare(b, 'ru'));
  currentRegions.forEach(region => {
    if (uniqueRegions.includes(region)) return;
    uniqueRegions.push(region);
    state.selectedRegions.add(region);
    addRegionCheckbox(region);
  });
  uniqueRegions.sort((a, b) => a.localeCompare(b, 'ru'));
}

document.getElementById('regionsAll').addEventListener('click', () => {
  state.selectedRegions = new Set(uniqueRegions);
  regionListEl.querySelectorAll('input').forEach(cb => cb.checked = true);
  render();
});
document.getElementById('regionsNone').addEventListener('click', () => {
  state.selectedRegions = new Set();
  regionListEl.querySelectorAll('input').forEach(cb => cb.checked = false);
  render();
});

const typeListEl = document.getElementById('typeList');
Object.entries(INCIDENT_TYPES).forEach(([key, def]) => {
  const label = document.createElement('label');
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = true;
  cb.addEventListener('change', () => {
    if (cb.checked) state.selectedTypes.add(key);
    else state.selectedTypes.delete(key);
    render();
  });
  const swatch = document.createElement('span');
  swatch.className = 'type-swatch';
  swatch.style.background = def.color;
  label.appendChild(cb);
  label.appendChild(swatch);
  label.appendChild(document.createTextNode(def.label));
  typeListEl.appendChild(label);
});

// ---------- Диапазон лет (двойной слайдер) ----------
const yearFromInput = document.getElementById('yearFrom');
const yearToInput = document.getElementById('yearTo');
const yearFromLabel = document.getElementById('yearFromLabel');
const yearToLabel = document.getElementById('yearToLabel');
const dualTrack = document.getElementById('dualTrack');
const chronoSlider = document.getElementById('chronoSlider');
const chronoYearLabel = document.getElementById('chronoYearLabel');

function updateDualTrackVisual() {
  const from = Number(yearFromInput.value);
  const to = Number(yearToInput.value);
  const pctFrom = ((from - MIN_YEAR) / (MAX_YEAR - MIN_YEAR)) * 100;
  const pctTo = ((to - MIN_YEAR) / (MAX_YEAR - MIN_YEAR)) * 100;
  dualTrack.style.background =
    `linear-gradient(to right, #2a3350 ${pctFrom}%, var(--accent) ${pctFrom}%, var(--accent) ${pctTo}%, #2a3350 ${pctTo}%)`;
}

function onYearRangeChange() {
  let from = Number(yearFromInput.value);
  let to = Number(yearToInput.value);
  if (from > to) { from = to; yearFromInput.value = from; }
  state.yearFrom = from;
  state.yearTo = to;

  // Синхронизируем диапазон слайдера хронологии
  chronoSlider.min = from;
  chronoSlider.max = to;
  if (state.chronoYear < from) state.chronoYear = from;
  if (state.chronoYear > to) state.chronoYear = to;
  chronoSlider.value = state.chronoYear;
  chronoYearLabel.textContent = state.chronoYear;

  yearFromLabel.textContent = from;
  yearToLabel.textContent = to;
  updateDualTrackVisual();
  render();
}

yearFromInput.addEventListener('input', onYearRangeChange);
yearToInput.addEventListener('input', onYearRangeChange);

// ---------- Хронология ----------
const playBtn = document.getElementById('playBtn');
const resetBtn = document.getElementById('resetBtn');
const onlyCurrentYearCb = document.getElementById('onlyCurrentYear');
const speedSelect = document.getElementById('speedSelect');

chronoSlider.addEventListener('input', () => {
  stopPlaying();
  state.chronoYear = Number(chronoSlider.value);
  chronoYearLabel.textContent = state.chronoYear;
  render();
});

onlyCurrentYearCb.addEventListener('change', () => {
  state.onlyCurrentYear = onlyCurrentYearCb.checked;
  render();
});

function stepPlay() {
  if (state.chronoYear >= state.yearTo) {
    stopPlaying();
    return;
  }
  state.chronoYear++;
  chronoSlider.value = state.chronoYear;
  chronoYearLabel.textContent = state.chronoYear;
  render();
}

function startPlaying() {
  if (state.chronoYear >= state.yearTo) {
    state.chronoYear = state.yearFrom;
  }
  state.playing = true;
  playBtn.textContent = '⏸ Пауза';
  state.playTimer = setInterval(stepPlay, Number(speedSelect.value));
}

function stopPlaying() {
  state.playing = false;
  playBtn.textContent = '▶ Хронология';
  if (state.playTimer) {
    clearInterval(state.playTimer);
    state.playTimer = null;
  }
}

playBtn.addEventListener('click', () => {
  if (state.playing) stopPlaying();
  else startPlaying();
});

speedSelect.addEventListener('change', () => {
  if (state.playing) {
    stopPlaying();
    startPlaying();
  }
});

resetBtn.addEventListener('click', () => {
  stopPlaying();
  yearFromInput.value = MIN_YEAR;
  yearToInput.value = MAX_YEAR;
  state.yearFrom = MIN_YEAR;
  state.yearTo = MAX_YEAR;
  state.chronoYear = MAX_YEAR;
  onlyCurrentYearCb.checked = false;
  state.onlyCurrentYear = false;
  chronoSlider.min = MIN_YEAR;
  chronoSlider.max = MAX_YEAR;
  chronoSlider.value = MAX_YEAR;
  chronoYearLabel.textContent = MAX_YEAR;
  yearFromLabel.textContent = MIN_YEAR;
  yearToLabel.textContent = MAX_YEAR;
  updateDualTrackVisual();
  state.selectedRegions = new Set(uniqueRegions);
  state.selectedTypes = new Set(Object.keys(INCIDENT_TYPES));
  regionListEl.querySelectorAll('input').forEach(cb => cb.checked = true);
  typeListEl.querySelectorAll('input').forEach(cb => cb.checked = true);
  closeDetail();
  render();
});

// ---------- Детальная панель ----------
const detailPanel = document.getElementById('detailPanel');
const detailContent = document.getElementById('detailContent');
document.getElementById('closeDetail').addEventListener('click', closeDetail);

function closeDetail() {
  detailPanel.classList.add('hidden');
}

function openDetail(incident) {
  const typeDef = INCIDENT_TYPES[incident.type];
  const isDrone = incident.type === 'drone_strike' || incident.type === 'drone_intercept_night';
  const targetRow = incident.target ? `
    <div class="detail-row">
      <span class="label">Объект</span>
      ${incident.target}
    </div>` : '';
  detailContent.innerHTML = `
    <div class="detail-badge" style="background:${typeDef.color}">${typeDef.label}</div>
    <h3 class="detail-title">${incident.name}</h3>

    <div class="detail-row">
      <span class="label">Дата</span>
      ${formatDate(incident.date)}
    </div>
    <div class="detail-row">
      <span class="label">Регион</span>
      ${incident.region}
    </div>
    ${targetRow}
    <div class="detail-row">
      <span class="label">Жертвы (оценка)</span>
      Погибших: ${incident.killed} · Пострадавших: ${incident.injured}
    </div>
    <div class="detail-row">
      <span class="label">Описание</span>
      ${incident.description}
    </div>
    <div class="detail-row">
      <span class="label">${isDrone ? 'Статус / последствия' : 'Статус расследования'}</span>
      ${incident.status}
    </div>
    <div class="detail-source">
      Источник: ${incident.sourceUrl
        ? `<a href="${incident.sourceUrl}" target="_blank" rel="noopener noreferrer">${incident.source}</a>`
        : incident.source}
    </div>
    ${incident.sourceUrl ? `
    <a class="proof-link" href="${incident.sourceUrl}" target="_blank" rel="noopener noreferrer">
      📄 Открыть новость-первоисточник →
    </a>` : ''}
  `;
  detailPanel.classList.remove('hidden');
}

function formatDate(iso) {
  const [y, m, d] = iso.split('-');
  const months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
  return `${Number(d)} ${months[Number(m) - 1]} ${y}`;
}

// ---------- Фильтрация и рендер ----------
function passesFilters(incident) {
  if (!state.selectedRegions.has(incident.region)) return false;
  if (!state.selectedTypes.has(incident.type)) return false;
  if (incident.year < state.yearFrom || incident.year > state.yearTo) return false;

  if (state.onlyCurrentYear) {
    return incident.year === state.chronoYear;
  }
  return incident.year <= state.chronoYear;
}

function render() {
  markersLayer.clearLayers();
  Object.keys(markerById).forEach(k => delete markerById[k]);

  const visible = allIncidents.filter(passesFilters);

  visible.forEach(incident => {
    const marker = L.marker(incident.coords, { icon: makeIcon(incident.type, false) });
    marker.bindPopup(`
      <div class="popup-title">${incident.name}</div>
      <div>${formatDate(incident.date)} · ${incident.region}</div>
      <div>Погибших: ${incident.killed}, пострадавших: ${incident.injured}</div>
    `);
    // Клик по маркеру сразу открывает полную карточку с пруфом — отдельная
    // ссылка "Подробнее" в попапе была лишней (дублировала это же действие).
    marker.on('click', () => openDetail(incident));
    marker.addTo(markersLayer);
    markerById[incident.id] = marker;
  });

  document.getElementById('statCount').textContent = visible.length;
  document.getElementById('statKilled').textContent = visible.reduce((s, i) => s + i.killed, 0);
  document.getElementById('statInjured').textContent = visible.reduce((s, i) => s + i.injured, 0);
}

// ---------- Автообновление: удары БПЛА ----------
// drone-strikes.json обновляется отдельно (в т.ч. по расписанию, вне этого
// приложения) и подтягивается сюда периодическим опросом (поллингом), чтобы
// карта отражала свежие данные без перезагрузки страницы или передеплоя.
const DRONE_DATA_URLS = [
  'https://raw.githubusercontent.com/IIIypuk-hash/TMap/main/drone-strikes.json',
  'drone-strikes.json', // локальный фолбэк, если raw.githubusercontent.com недоступен
];
const DRONE_POLL_INTERVAL_MS = 5 * 60 * 1000; // 5 минут
const seenDroneIds = new Set();
let droneLastUpdated = null;

const droneUpdatedEl = document.getElementById('droneUpdated');
const droneCountEl = document.getElementById('droneCount');
const refreshDroneBtn = document.getElementById('refreshDroneBtn');

async function fetchDroneStrikes() {
  refreshDroneBtn.disabled = true;
  refreshDroneBtn.textContent = '⟳ Обновление…';
  let ok = false;
  for (const baseUrl of DRONE_DATA_URLS) {
    try {
      const sep = baseUrl.includes('?') ? '&' : '?';
      const res = await fetch(`${baseUrl}${sep}t=${Date.now()}`, { cache: 'no-store' });
      if (!res.ok) continue;
      const data = await res.json();
      mergeDroneStrikes(data);
      ok = true;
      break;
    } catch (e) {
      // пробуем следующий источник
    }
  }
  refreshDroneBtn.disabled = false;
  refreshDroneBtn.textContent = '⟳ Обновить сейчас';
  if (!ok) {
    droneUpdatedEl.textContent = 'ошибка загрузки';
  }
  return ok;
}

function mergeDroneStrikes(data) {
  let added = false;
  (data.strikes || []).forEach(s => {
    if (seenDroneIds.has(s.id)) return;
    seenDroneIds.add(s.id);
    allIncidents.push({
      id: s.id,
      date: s.date,
      year: Number(String(s.date).slice(0, 4)),
      name: s.name,
      type: 'drone_strike',
      region: s.region,
      coords: s.coords,
      killed: s.killed || 0,
      injured: s.injured || 0,
      status: s.status,
      description: s.description,
      source: s.source,
      sourceUrl: s.sourceUrl,
      target: s.target,
    });
    added = true;
  });
  if (data.generated_at) droneLastUpdated = data.generated_at;

  if (added) rebuildRegionList();
  updateDroneStatusUI();
  if (added) render();
}

function updateDroneStatusUI() {
  droneCountEl.textContent = allIncidents.filter(i => i.type === 'drone_strike').length;
  droneUpdatedEl.textContent = droneLastUpdated ? formatDateTime(droneLastUpdated) : '—';
}

function formatDateTime(iso) {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

refreshDroneBtn.addEventListener('click', () => fetchDroneStrikes());

// ---------- Автообновление: ночные сводки ПВО по регионам ----------
// Отдельный, гораздо более многочисленный слой: там, где источник называет
// только регион и общее число сбитых БПЛА за ночь, но не точку падения.
// Каждая (дата, регион) получает небольшое детерминированное смещение вокруг
// центра региона, чтобы десятки ночей по одному региону не сливались в одну
// точку на карте — это не точные координаты, а визуальная развёртка.
const AGGREGATE_DATA_URLS = [
  'https://raw.githubusercontent.com/IIIypuk-hash/TMap/main/drone-aggregate.json',
  'drone-aggregate.json',
];
const seenAggregateIds = new Set();
let aggregateLastUpdated = null;
const aggregateUpdatedEl = document.getElementById('aggregateUpdated');
const aggregateCountEl = document.getElementById('aggregateCount');
const refreshAggregateBtn = document.getElementById('refreshAggregateBtn');

function jitterCoords(baseCoords, seedStr, radiusDeg) {
  // Простой детерминированный хэш строки -> два псевдослучайных числа,
  // чтобы одна и та же (дата, регион) всегда давала одно и то же смещение.
  let h1 = 0, h2 = 0;
  for (let i = 0; i < seedStr.length; i++) {
    h1 = (h1 * 31 + seedStr.charCodeAt(i)) >>> 0;
    h2 = (h2 * 131 + seedStr.charCodeAt(i)) >>> 0;
  }
  const angle = (h1 % 3600) / 3600 * Math.PI * 2;
  const dist = ((h2 % 1000) / 1000) * radiusDeg;
  return [baseCoords[0] + Math.cos(angle) * dist, baseCoords[1] + Math.sin(angle) * dist * 1.5];
}

async function fetchDroneAggregate() {
  refreshAggregateBtn.disabled = true;
  refreshAggregateBtn.textContent = '⟳ Обновление…';
  let ok = false;
  for (const baseUrl of AGGREGATE_DATA_URLS) {
    try {
      const sep = baseUrl.includes('?') ? '&' : '?';
      const res = await fetch(`${baseUrl}${sep}t=${Date.now()}`, { cache: 'no-store' });
      if (!res.ok) continue;
      const data = await res.json();
      mergeDroneAggregate(data);
      ok = true;
      break;
    } catch (e) {
      // пробуем следующий источник
    }
  }
  refreshAggregateBtn.disabled = false;
  refreshAggregateBtn.textContent = '⟳ Обновить сейчас';
  if (!ok) aggregateUpdatedEl.textContent = 'ошибка загрузки';
  return ok;
}

function mergeDroneAggregate(data) {
  let added = false;
  (data.nights || []).forEach(night => {
    (night.regions || []).forEach(r => {
      const id = `agg-${night.date}-${r.region}`;
      if (seenAggregateIds.has(id)) return;
      const base = REGION_CENTROIDS[r.region];
      if (!base) {
        console.warn('Нет координат для региона агрегата ПВО:', r.region);
        return;
      }
      seenAggregateIds.add(id);
      const coords = jitterCoords(base, id, 0.12);
      const countText = r.count != null ? `сбито ${r.count} БПЛА над регионом` : 'регион в зоне отражения атаки';
      const totalText = night.national_total != null ? `; всего по стране в эту ночь — ${night.national_total}` : '';
      allIncidents.push({
        id,
        date: night.date,
        year: Number(String(night.date).slice(0, 4)),
        name: `Ночь на ${formatDate(night.date)}: ${r.region}`,
        type: 'drone_intercept_night',
        region: r.region,
        coords,
        killed: 0,
        injured: 0,
        status: 'Ночная сводка ПВО, не точечный инцидент',
        description: `По сводке Минобороны, в эту ночь ${countText}${totalText}. Точка на карте — не место падения, а условное положение около центра региона (см. пояснение слоя).`,
        source: 'Сводки Минобороны РФ (пересказ СМИ)',
        sourceUrl: night.sourceUrl,
        target: null,
      });
      added = true;
    });
  });
  if (data.generated_at) aggregateLastUpdated = data.generated_at;
  if (added) rebuildRegionList();
  updateAggregateStatusUI();
  if (added) render();
}

function updateAggregateStatusUI() {
  aggregateCountEl.textContent = allIncidents.filter(i => i.type === 'drone_intercept_night').length;
  aggregateUpdatedEl.textContent = aggregateLastUpdated ? formatDateTime(aggregateLastUpdated) : '—';
}

refreshAggregateBtn.addEventListener('click', () => fetchDroneAggregate());

// ---------- Инициализация ----------
chronoYearLabel.textContent = state.chronoYear;
chronoSlider.value = state.chronoYear;
updateDualTrackVisual();
render();

fetchDroneStrikes();
fetchDroneAggregate();
setInterval(fetchDroneStrikes, DRONE_POLL_INTERVAL_MS);
setInterval(fetchDroneAggregate, DRONE_POLL_INTERVAL_MS);
