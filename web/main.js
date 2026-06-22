const REGION_LABELS = {
  pangyo: "판교 제1테크노밸리",
  cheongna: "청라 국제업무지구",
};

const regionSelect = document.querySelector("#region-select");
const timeSelect = document.querySelector("#time-select");
const mapState = document.querySelector("#map-state");
const workersValue = document.querySelector("#workers-value");
const populationValue = document.querySelector("#population-value");
const districtEmploymentValue = document.querySelector("#district-employment-value");
const coreStationValue = document.querySelector("#core-station-value");
const selectedRegionLabel = document.querySelector("#selected-region-label");
const compareGrid = document.querySelector("#compare-grid");
const curveChart = document.querySelector("#curve-chart");
const layerButtons = document.querySelectorAll(".layer-button");

const colorSchemes = {
  landuse: {
    "주거": "#d96c3f",
    "상업": "#f1a208",
    "상업/근생": "#f1a208",
    "업무": "#0f6c5c",
    "교육연구": "#1f78b4",
    "산업/물류": "#6f5ef9",
    "녹지": "#4caf50",
    "기반시설": "#6c757d",
    "기타": "#c6a56b",
  },
  demographics: ["#eff6f3", "#cbe5dd", "#7ac0ab", "#2b8c74", "#115746"],
};

let activeLayer = "landuse";
let appData = null;
let map = null;
let boundaryLayer = null;
let thematicLayer = null;
let isochroneLayer = null;
const regionCache = {};

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to load ${path}`);
  }
  return response.json();
}

async function loadData() {
  return fetchJson("../processed/summary.json");
}

async function ensureRegionData(region) {
  if (regionCache[region]) return regionCache[region];
  const base = `../processed/${region}`;
  const payload = {
    boundary: await fetchJson(`${base}/${region}_boundary.geojson`),
    buildings: await fetchJson(`${base}/${region}_buildings.geojson`),
    sgis: await fetchJson(`${base}/${region}_sgis.geojson`),
    isochrones: await fetchJson(`${base}/${region}_isochrones.geojson`),
    stations: await fetchJson(`${base}/${region}_reachable_stations.geojson`),
  };
  regionCache[region] = payload;
  return payload;
}

function initMap() {
  map = L.map("map", { zoomControl: true, preferCanvas: true }).setView([37.45, 127.05], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
}

function topCategory(obj) {
  const entries = Object.entries(obj || {});
  if (!entries.length) return "-";
  entries.sort((a, b) => b[1] - a[1]);
  const [label, value] = entries[0];
  return `${label} ${(value * 100).toFixed(1)}%`;
}

function formatNumber(value) {
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value || 0);
}

function updateStats(region, minute) {
  const summary = appData[region].summary;
  const transport = summary.transport;
  const totals = transport.isochrone_totals[String(minute)];

  selectedRegionLabel.textContent = REGION_LABELS[region];
  coreStationValue.textContent = `${transport.core_station_name} (${transport.core_station_lines.join(", ")})`;
  workersValue.textContent = `${formatNumber(totals.employment)}명`;
  populationValue.textContent = `${formatNumber(totals.population)}명`;
  districtEmploymentValue.textContent = `${formatNumber(summary.sgis_totals.employment)}명`;
}

function updateCompare(minute) {
  const rows = [
    {
      title: `${minute}분 도달 종사자`,
      pangyo: `${formatNumber(appData.pangyo.summary.transport.isochrone_totals[String(minute)].employment)}명`,
      cheongna: `${formatNumber(appData.cheongna.summary.transport.isochrone_totals[String(minute)].employment)}명`,
    },
    {
      title: `${minute}분 도달 인구`,
      pangyo: `${formatNumber(appData.pangyo.summary.transport.isochrone_totals[String(minute)].population)}명`,
      cheongna: `${formatNumber(appData.cheongna.summary.transport.isochrone_totals[String(minute)].population)}명`,
    },
    {
      title: `구역 내 종사자`,
      pangyo: `${formatNumber(appData.pangyo.summary.sgis_totals.employment)}명`,
      cheongna: `${formatNumber(appData.cheongna.summary.sgis_totals.employment)}명`,
    },
    {
      title: `대표 토지이용`,
      pangyo: topCategory(appData.pangyo.summary.landuse_ratio),
      cheongna: topCategory(appData.cheongna.summary.landuse_ratio),
    },
    {
      title: `대표 건축물 용도`,
      pangyo: topCategory(appData.pangyo.summary.building_use_ratio_by_floor_area),
      cheongna: topCategory(appData.cheongna.summary.building_use_ratio_by_floor_area),
    },
  ];

  compareGrid.innerHTML = rows.map((row) => `
    <article class="compare-row">
      <h3>${row.title}</h3>
      <div class="compare-values">
        <div class="compare-item"><strong>판교</strong><span>${row.pangyo}</span></div>
        <div class="compare-item"><strong>청라</strong><span>${row.cheongna}</span></div>
      </div>
    </article>
  `).join("");
}

function renderCurveChart() {
  const width = 640;
  const height = 260;
  const margin = { top: 20, right: 20, bottom: 32, left: 50 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const pCurve = appData.pangyo.summary.transport.accessibility_curve;
  const cCurve = appData.cheongna.summary.transport.accessibility_curve;
  const maxY = Math.max(
    ...pCurve.map((d) => d.employment),
    ...cCurve.map((d) => d.employment),
  );

  const x = (minute) => margin.left + (minute / 60) * innerW;
  const y = (value) => margin.top + innerH - (value / maxY) * innerH;
  const pathFor = (curve) => curve.map((d, i) => `${i === 0 ? "M" : "L"} ${x(d.minute)} ${y(d.employment)}`).join(" ");
  const tickLines = [0, 15, 30, 45, 60].map((minute) => `
    <line x1="${x(minute)}" y1="${margin.top}" x2="${x(minute)}" y2="${margin.top + innerH}" stroke="rgba(0,0,0,0.08)" />
    <text x="${x(minute)}" y="${height - 8}" text-anchor="middle" font-size="12" fill="#60707a">${minute}</text>
  `).join("");
  const yLabels = [0, maxY / 2, maxY].map((value) => `
    <text x="10" y="${y(value) + 4}" font-size="12" fill="#60707a">${formatNumber(value)}</text>
  `).join("");

  curveChart.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="transparent"></rect>
    ${tickLines}
    ${yLabels}
    <path d="${pathFor(pCurve)}" fill="none" stroke="#0f6c5c" stroke-width="4" stroke-linecap="round"></path>
    <path d="${pathFor(cCurve)}" fill="none" stroke="#d96c3f" stroke-width="4" stroke-linecap="round"></path>
    <circle cx="${width - 160}" cy="28" r="6" fill="#0f6c5c"></circle>
    <text x="${width - 148}" y="32" font-size="12" fill="#1d2a33">판교 도달 종사자</text>
    <circle cx="${width - 160}" cy="50" r="6" fill="#d96c3f"></circle>
    <text x="${width - 148}" y="54" font-size="12" fill="#1d2a33">청라 도달 종사자</text>
  `;
}

function buildingStyle(feature) {
  const use = feature.properties.building_use_group || "기타";
  return {
    color: "#ffffff",
    weight: 0.4,
    fillColor: colorSchemes.landuse[use] || colorSchemes.landuse["기타"],
    fillOpacity: 0.72,
  };
}

function demographicStyle(feature, values) {
  const v = feature.properties.weighted_employment || 0;
  const breaks = values;
  let fill = colorSchemes.demographics[0];
  if (v > breaks[3]) fill = colorSchemes.demographics[4];
  else if (v > breaks[2]) fill = colorSchemes.demographics[3];
  else if (v > breaks[1]) fill = colorSchemes.demographics[2];
  else if (v > breaks[0]) fill = colorSchemes.demographics[1];
  return {
    color: "#f8f5ef",
    weight: 0.6,
    fillColor: fill,
    fillOpacity: 0.78,
  };
}

function quantileBreaks(features) {
  const values = features
    .map((feature) => Number(feature.properties.weighted_employment || 0))
    .sort((a, b) => a - b);
  const idx = (p) => values[Math.min(values.length - 1, Math.floor(values.length * p))] || 0;
  return [idx(0.25), idx(0.5), idx(0.75), idx(0.9)];
}

function clearLayers() {
  [boundaryLayer, thematicLayer, isochroneLayer].forEach((layer) => {
    if (layer) map.removeLayer(layer);
  });
}

async function renderMap(region, minute) {
  clearLayers();
  mapState.textContent = "지도 데이터 불러오는 중";
  const dataset = await ensureRegionData(region);

  boundaryLayer = L.geoJSON(dataset.boundary, {
    style: {
      color: "#122630",
      weight: 2.2,
      fillOpacity: 0.02,
    },
  }).addTo(map);

  if (activeLayer === "landuse") {
    thematicLayer = L.geoJSON(dataset.buildings, {
      style: buildingStyle,
      onEachFeature(feature, layer) {
        const props = feature.properties;
        layer.bindPopup(`
          <strong>${props.building_use_group || "기타"}</strong><br />
          연면적: ${formatNumber(props.gross_floor_area_m2)}㎡<br />
          대지면적: ${formatNumber(props.site_area_m2)}㎡<br />
          용적률: ${Number(props.floor_area_ratio_pct || 0).toFixed(1)}%
        `);
      },
    }).addTo(map);
    mapState.textContent = `${REGION_LABELS[region]} · 건축물 주용도`;
  } else if (activeLayer === "transport") {
    const filteredIsochrone = {
      ...dataset.isochrones,
      features: dataset.isochrones.features.filter((feature) => Number(feature.properties.minutes) === Number(minute)),
    };
    thematicLayer = L.geoJSON(filteredIsochrone, {
      style: {
        color: "#d96c3f",
        weight: 2,
        fillColor: "#d96c3f",
        fillOpacity: 0.26,
      },
      onEachFeature(feature, layer) {
        layer.bindPopup(`
          <strong>${feature.properties.minutes}분 등시시간권</strong><br />
          도달 인구: ${formatNumber(feature.properties.population)}명<br />
          도달 종사자: ${formatNumber(feature.properties.employment)}명
        `);
      },
    }).addTo(map);

    isochroneLayer = L.geoJSON(dataset.stations, {
      pointToLayer(feature, latlng) {
        return L.circleMarker(latlng, {
          radius: 3,
          color: "#0f6c5c",
          weight: 1,
          fillColor: "#0f6c5c",
          fillOpacity: 0.85,
        });
      },
      onEachFeature(feature, layer) {
        layer.bindPopup(`
          <strong>${feature.properties.statnm}</strong><br />
          노선: ${feature.properties.linenm}<br />
          소요시간: ${Number(feature.properties.travel_time_min).toFixed(1)}분
        `);
      },
    }).addTo(map);
    mapState.textContent = `${REGION_LABELS[region]} · ${minute}분 등시시간권`;
  } else {
    const breaks = quantileBreaks(dataset.sgis.features);
    thematicLayer = L.geoJSON(dataset.sgis, {
      style: (feature) => demographicStyle(feature, breaks),
      onEachFeature(feature, layer) {
        layer.bindPopup(`
          <strong>집계구 ${feature.properties.TOT_OA_CD}</strong><br />
          가중 인구: ${formatNumber(feature.properties.weighted_population)}명<br />
          가중 종사자: ${formatNumber(feature.properties.weighted_employment)}명
        `);
      },
    }).addTo(map);
    mapState.textContent = `${REGION_LABELS[region]} · 집계구 인구/종사자`;
  }

  map.fitBounds(boundaryLayer.getBounds(), { padding: [24, 24] });
}

async function render() {
  const region = regionSelect.value;
  const minute = timeSelect.value;
  updateStats(region, minute);
  updateCompare(minute);
  renderCurveChart();
  try {
    await renderMap(region, minute);
  } catch (error) {
    console.error(error);
    mapState.textContent = "지도 데이터 로드 실패";
  }
}

layerButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activeLayer = button.dataset.layer;
    layerButtons.forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    render();
  });
});

regionSelect.addEventListener("change", render);
timeSelect.addEventListener("change", render);

async function main() {
  initMap();
  const summary = await loadData();
  appData = {
    pangyo: { summary: summary.pangyo },
    cheongna: { summary: summary.cheongna },
  };
  await render();
}

main().catch((error) => {
  mapState.textContent = "데이터 로드 실패";
  console.error(error);
});
