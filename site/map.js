"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let allEvents = [];
let selectedSources = new Set();
let map = null;
let cluster = null;

function toISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function todayISO()    { return toISO(new Date()); }
function oneMonthISO() {
  const d = new Date();
  d.setMonth(d.getMonth() + 1);
  return toISO(d);
}

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);

const searchInput       = $("search");
const filterKids        = $("filter-kids");
const filterDateFrom    = $("filter-date-from");
const filterDateTo      = $("filter-date-to");
const resetBtn          = $("reset-filters");
const resultCount       = $("result-count");
const metaUpdated       = $("meta-updated");
const metaCounts        = $("meta-counts");
const geocodedPct       = $("geocoded-pct");
const sourceFilterWrap  = $("source-filter-wrap");
const sourceFilterBtn   = $("source-filter-btn");
const sourceFilterPanel = $("source-filter-panel");
const sourceFilterLabel = $("source-filter-label");

// ---------------------------------------------------------------------------
// Source filter dropdown
// ---------------------------------------------------------------------------
function updateSourceLabel() {
  if (selectedSources.size === 0) {
    sourceFilterLabel.textContent = "All sources";
  } else {
    sourceFilterLabel.textContent = `${selectedSources.size} source${selectedSources.size > 1 ? "s" : ""}`;
  }
}

function buildSourceCheckboxes(sources) {
  sourceFilterPanel.innerHTML = "";
  sources.forEach((src) => {
    const label = document.createElement("label");
    label.className = "flex items-center gap-2 cursor-pointer text-sm text-slate-700 hover:text-slate-900 py-0.5";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = src;
    cb.className = "rounded border-slate-300 text-sky-500 focus:ring-sky-400";
    cb.addEventListener("change", () => {
      if (cb.checked) selectedSources.add(src);
      else selectedSources.delete(src);
      updateSourceLabel();
      render();
    });

    label.appendChild(cb);
    label.appendChild(document.createTextNode(src));
    sourceFilterPanel.appendChild(label);
  });
}

sourceFilterBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  sourceFilterPanel.classList.toggle("hidden");
});
document.addEventListener("click", (e) => {
  if (!sourceFilterWrap.contains(e.target)) {
    sourceFilterPanel.classList.add("hidden");
  }
});

// ---------------------------------------------------------------------------
// Filtering (mirrors app.js logic, minus hidden-titles for now)
// ---------------------------------------------------------------------------
function passesFilters(ev) {
  if (filterKids.checked && !ev.is_kids_event) return false;

  const dateFrom = filterDateFrom.value;
  const dateTo   = filterDateTo.value;
  if (dateFrom && ev.date_start < dateFrom) return false;
  if (dateTo   && ev.date_start > dateTo)   return false;

  if (selectedSources.size > 0 && !selectedSources.has(ev.source)) return false;

  const q = searchInput.value.trim().toLowerCase();
  if (q) {
    const hay = `${ev.title} ${ev.description || ""} ${ev.location || ""}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------
function fmtDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function fmtTime(t) {
  if (!t) return "";
  const [h, m] = t.split(":").map(Number);
  const suffix = h >= 12 ? "pm" : "am";
  const h12 = h % 12 || 12;
  return m ? `${h12}:${String(m).padStart(2, "0")}${suffix}` : `${h12}${suffix}`;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
function render() {
  const visible = allEvents.filter(passesFilters);

  // Group by venue coordinates (lat,lng rounded).
  const groups = new Map();
  for (const ev of visible) {
    if (ev.lat == null || ev.lng == null) continue;
    const key = `${ev.lat.toFixed(5)},${ev.lng.toFixed(5)}`;
    if (!groups.has(key)) {
      groups.set(key, {
        lat: ev.lat,
        lng: ev.lng,
        venue: ev.venue_name || ev.location,
        events: [],
      });
    }
    groups.get(key).events.push(ev);
  }

  // Reset cluster layer
  cluster.clearLayers();

  let onMapCount = 0;
  for (const g of groups.values()) {
    g.events.sort((a, b) =>
      a.date_start === b.date_start
        ? (a.time_start || "").localeCompare(b.time_start || "")
        : a.date_start.localeCompare(b.date_start)
    );
    onMapCount += g.events.length;

    const kidsOnly = g.events.every((e) => e.is_kids_event);
    const count = g.events.length;
    const icon = L.divIcon({
      className: "", // suppress default leaflet styling
      html: `<div class="venue-marker ${kidsOnly ? "kids" : ""}">${count}</div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
    });

    const marker = L.marker([g.lat, g.lng], { icon });
    marker.bindPopup(buildPopup(g), { maxWidth: 280 });
    cluster.addLayer(marker);
  }

  resultCount.textContent = `${visible.length} events (${onMapCount} on map)`;
}

function buildPopup(group) {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

  const items = group.events.slice(0, 20).map((ev) => {
    const timeBit = ev.time_start ? ` · ${fmtTime(ev.time_start)}` : "";
    return `
      <div class="popup-event">
        <div class="popup-event-title">${esc(ev.title)}</div>
        <div class="popup-event-date">${fmtDate(ev.date_start)}${timeBit}</div>
        <a href="${esc(ev.url)}" target="_blank" rel="noopener">Details →</a>
      </div>
    `;
  }).join("");

  const moreNote = group.events.length > 20
    ? `<div class="text-xs text-slate-400 mt-1">+${group.events.length - 20} more</div>`
    : "";

  return `
    <div class="popup-venue-name">${esc(group.venue)}</div>
    <div class="popup-count">${group.events.length} event${group.events.length === 1 ? "" : "s"}</div>
    <div class="popup-events">${items}</div>
    ${moreNote}
  `;
}

// ---------------------------------------------------------------------------
// Initialize map
// ---------------------------------------------------------------------------
function initMap() {
  // Default view centered on Bay Area
  map = L.map("map", { scrollWheelZoom: true }).setView([37.35, -121.95], 10);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(map);

  cluster = L.markerClusterGroup({
    showCoverageOnHover: false,
    maxClusterRadius: 40,
  });
  map.addLayer(cluster);
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
async function loadEvents() {
  try {
    const resp = await fetch(`data/events.json?t=${Date.now()}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    allEvents = data.events || [];

    // Meta
    metaUpdated.textContent = `Updated ${new Date(data.updated_at).toLocaleDateString()}`;
    metaCounts.textContent  = `${data.total} events · ${data.kids_total} kids/family`;

    if (data.geocoded_total != null && data.total > 0) {
      geocodedPct.textContent = `${Math.round(100 * data.geocoded_total / data.total)}%`;
    }

    // Build source filter
    buildSourceCheckboxes(data.sources || []);

    // Fit view to geocoded events if any
    const geo = allEvents.filter((e) => e.lat != null);
    if (geo.length > 0) {
      const bounds = L.latLngBounds(geo.map((e) => [e.lat, e.lng]));
      map.fitBounds(bounds.pad(0.15));
    }

    render();
  } catch (exc) {
    console.error(exc);
    resultCount.textContent = `Error loading events: ${exc.message}`;
  }
}

// Event listeners
[searchInput, filterDateFrom, filterDateTo].forEach(
  (el) => el.addEventListener("input", render)
);
filterKids.addEventListener("change", render);

resetBtn.addEventListener("click", () => {
  searchInput.value     = "";
  filterKids.checked    = false;
  filterDateFrom.value  = todayISO();
  filterDateTo.value    = oneMonthISO();
  selectedSources.clear();
  sourceFilterPanel.querySelectorAll("input[type=checkbox]").forEach((cb) => {
    cb.checked = false;
  });
  updateSourceLabel();
  render();
});

filterDateFrom.value = todayISO();
filterDateTo.value   = oneMonthISO();
initMap();
loadEvents();
