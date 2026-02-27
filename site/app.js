"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let allEvents = [];
let selectedSources = new Set(); // empty = "all sources"

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);

const loading    = $("loading");
const errorMsg   = $("error-msg");
const errorText  = $("error-text");
const grid       = $("events-grid");
const noResults  = $("no-results");
const cardTpl    = $("card-tpl");

const searchInput       = $("search");
const filterKids        = $("filter-kids");
const filterDateFrom    = $("filter-date-from");
const filterDateTo      = $("filter-date-to");
const resetBtn          = $("reset-filters");
const resultCount       = $("result-count");
const metaUpdated       = $("meta-updated");
const metaCounts        = $("meta-counts");
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

// Toggle panel open/close
sourceFilterBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  sourceFilterPanel.classList.toggle("hidden");
});

// Close when clicking outside
document.addEventListener("click", (e) => {
  if (!sourceFilterWrap.contains(e.target)) {
    sourceFilterPanel.classList.add("hidden");
  }
});

// ---------------------------------------------------------------------------
// Load data
// ---------------------------------------------------------------------------
async function loadEvents() {
  try {
    const res = await fetch("data/events.json?v=" + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    allEvents = data.events || [];

    // Meta header
    const updated = new Date(data.updated_at);
    metaUpdated.textContent = `Updated: ${updated.toLocaleDateString("en-US", { month:"short", day:"numeric", year:"numeric" })}`;
    metaCounts.textContent = `${data.total} events · ${data.kids_total} kids/family · ${data.library_total} library`;

    // Build source checkboxes
    const sources = [...new Set(allEvents.map((e) => e.source))].sort();
    buildSourceCheckboxes(sources);

    loading.classList.add("hidden");
    grid.classList.remove("hidden");
    render();
  } catch (err) {
    loading.classList.add("hidden");
    errorMsg.classList.remove("hidden");
    errorText.textContent = `Could not load events: ${err.message}`;
    console.error(err);
  }
}

// ---------------------------------------------------------------------------
// Filter
// ---------------------------------------------------------------------------
function getFiltered() {
  const q        = searchInput.value.trim().toLowerCase();
  const kidsOnly = filterKids.checked;
  const dateFrom = filterDateFrom.value;
  const dateTo   = filterDateTo.value;

  return allEvents.filter((ev) => {
    if (kidsOnly && !ev.is_kids_event)                               return false;
    if (selectedSources.size > 0 && !selectedSources.has(ev.source)) return false;
    if (dateFrom && ev.date_start < dateFrom)                   return false;
    if (dateTo   && ev.date_start > dateTo)                     return false;
    if (q) {
      const haystack = `${ev.title} ${ev.description || ""} ${ev.source} ${(ev.categories || []).join(" ")}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------
function fmt_date(ev) {
  const d = new Date(ev.date_start + "T00:00:00");
  const day = d.toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
  const time = ev.time_start ? fmt_time(ev.time_start) : "";
  const timeEnd = ev.time_end ? ` – ${fmt_time(ev.time_end)}` : "";
  return time ? `${day} · ${time}${timeEnd}` : day;
}

function fmt_time(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  const ampm = h >= 12 ? "PM" : "AM";
  const h12  = h % 12 || 12;
  return m ? `${h12}:${String(m).padStart(2,"0")} ${ampm}` : `${h12} ${ampm}`;
}

function makeCard(ev) {
  const node = cardTpl.content.cloneNode(true);
  const article = node.querySelector("article");

  article.style.animationDelay = "0ms";

  const q = (sel) => node.querySelector(sel);

  q(".card-title").textContent = ev.title;
  q(".card-date").textContent  = fmt_date(ev);

  if (ev.is_kids_event) {
    q(".card-kids-badge").classList.remove("hidden");
  }
  if (ev.location) {
    const locEl = q(".card-location");
    locEl.textContent = ev.location;
    locEl.classList.remove("hidden");
  }
  if (ev.description) {
    const descEl = q(".card-desc");
    descEl.textContent = ev.description;
    descEl.classList.remove("hidden");
  }
  if (ev.image_url) {
    const wrap = q(".card-img-wrap");
    wrap.classList.remove("hidden");
    q(".card-img").src = ev.image_url;
    q(".card-img").alt = ev.title;
  }

  // Source badge
  const badge = q(".card-source-badge");
  badge.textContent = ev.source;
  badge.classList.add(ev.source_type === "library" ? "badge-library" : "badge-city");

  // Link
  const link = q(".card-link");
  link.href = ev.url;
  link.title = `More info: ${ev.title}`;

  // Category tags
  const cats = (ev.categories || []).filter(Boolean).slice(0, 4);
  if (cats.length) {
    const catsEl = q(".card-cats");
    catsEl.classList.remove("hidden");
    cats.forEach((cat) => {
      const span = document.createElement("span");
      span.textContent = cat;
      span.className = "text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded";
      catsEl.appendChild(span);
    });
  }

  return node;
}

function render() {
  const filtered = getFiltered();
  resultCount.textContent = `${filtered.length} event${filtered.length !== 1 ? "s" : ""}`;

  grid.innerHTML = "";
  noResults.classList.add("hidden");

  if (filtered.length === 0) {
    noResults.classList.remove("hidden");
    return;
  }

  const CHUNK = 30;
  let i = 0;
  function renderChunk() {
    const frag = document.createDocumentFragment();
    const end = Math.min(i + CHUNK, filtered.length);
    for (; i < end; i++) {
      frag.appendChild(makeCard(filtered[i]));
    }
    grid.appendChild(frag);
    if (i < filtered.length) requestAnimationFrame(renderChunk);
  }
  renderChunk();
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------
[searchInput, filterDateFrom, filterDateTo].forEach(
  (el) => el.addEventListener("input", render)
);
filterKids.addEventListener("change", render);

resetBtn.addEventListener("click", () => {
  searchInput.value     = "";
  filterKids.checked    = false;
  filterDateFrom.value  = "";
  filterDateTo.value    = "";
  // Uncheck all source checkboxes
  selectedSources.clear();
  sourceFilterPanel.querySelectorAll("input[type=checkbox]").forEach((cb) => {
    cb.checked = false;
  });
  updateSourceLabel();
  render();
});

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
loadEvents();
