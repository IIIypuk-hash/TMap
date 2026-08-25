// app.js — логика карты, фильтров и режима хронологии

const MIN_YEAR = 1991;
const MAX_YEAR = 2026;

// ---------- Состояние ----------
const state = {
  selectedRegions: new Set(incidents.map(i => i.region)),
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

const markersLayer = L.layerGroup().addTo(map);
const markerById = {};

function makeIcon(type, highlighted) {
  const color = INCIDENT_TYPES[type]?.color || '#999';
  const size = highlighted ? 22 : 16;
  return L.divIcon({
    className: '',
    html: `<div style="
      width:${size}px;height:${size}px;border-radius:50%;
      background:${color};border:2px solid rgba(255,255,255,0.85);
      box-shadow:0 0 6px rgba(0,0,0,0.6);
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

// ---------- Построение списков фильтров ----------
const regionListEl = document.getElementById('regionList');
const uniqueRegions = [...new Set(incidents.map(i => i.region))].sort((a, b) => a.localeCompare(b, 'ru'));

uniqueRegions.forEach(region => {
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
});

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
    <div class="detail-row">
      <span class="label">Жертвы (оценка)</span>
      Погибших: ${incident.killed} · Пострадавших: ${incident.injured}
    </div>
    <div class="detail-row">
      <span class="label">Описание</span>
      ${incident.description}
    </div>
    <div class="detail-row">
      <span class="label">Статус расследования</span>
      ${incident.status}
    </div>
    <div class="detail-source">Источник: ${incident.source}</div>
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

  const visible = incidents.filter(passesFilters);

  visible.forEach(incident => {
    const marker = L.marker(incident.coords, { icon: makeIcon(incident.type, false) });
    marker.bindPopup(`
      <div class="popup-title">${incident.name}</div>
      <div>${formatDate(incident.date)} · ${incident.region}</div>
      <div>Погибших: ${incident.killed}, пострадавших: ${incident.injured}</div>
      <div class="popup-link" data-id="${incident.id}">Подробнее →</div>
    `);
    marker.on('popupopen', (e) => {
      const link = e.popup.getElement().querySelector('.popup-link');
      if (link) link.addEventListener('click', () => openDetail(incident));
    });
    marker.on('click', () => openDetail(incident));
    marker.addTo(markersLayer);
    markerById[incident.id] = marker;
  });

  document.getElementById('statCount').textContent = visible.length;
  document.getElementById('statKilled').textContent = visible.reduce((s, i) => s + i.killed, 0);
  document.getElementById('statInjured').textContent = visible.reduce((s, i) => s + i.injured, 0);
}

// ---------- Инициализация ----------
chronoYearLabel.textContent = state.chronoYear;
chronoSlider.value = state.chronoYear;
updateDualTrackVisual();
render();
