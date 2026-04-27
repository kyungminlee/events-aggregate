"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let allEvents = [];
let selectedSources = new Set(); // empty = "all sources"

// Local YYYY-MM-DD (not UTC, not locale-dependent). Called fresh each render
// so a tab left open across midnight still highlights the correct "today".
function toISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function todayISO()      { return toISO(new Date()); }
function oneMonthISO() {
  const d = new Date();
  d.setMonth(d.getMonth() + 1);
  return toISO(d);
}

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
const filterSaved       = $("filter-saved");
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

const hiddenWrap   = $("hidden-wrap");
const hiddenBtn    = $("hidden-btn");
const hiddenPanel  = $("hidden-panel");
const hiddenCount  = $("hidden-count");

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

  const savedOnly = filterSaved.checked;

  return allEvents.filter((ev) => {
    if (isTitleHidden(ev.title))                                     return false;
    if (kidsOnly && !ev.is_kids_event)                               return false;
    if (savedOnly && !isEventSaved(ev.id))                           return false;
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

  if (ev.date_start === todayISO()) {
    article.classList.add("ring-2", "ring-sky-400");
  }

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

  // Save (star) button
  const saveBtn = q(".card-save-btn");
  function paintSave() {
    const saved = isEventSaved(ev.id);
    saveBtn.textContent = saved ? "★" : "☆";
    saveBtn.classList.toggle("text-amber-500", saved);
    saveBtn.classList.toggle("text-slate-300", !saved);
    saveBtn.title = saved ? "Unsave event" : "Save event";
  }
  paintSave();
  saveBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    savedEventToggle(ev.id);
    paintSave();
    if (filterSaved.checked) render();
  });

  // Hide button
  q(".card-hide-btn").addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    hiddenTitleAdd(ev.title);
    refreshHiddenUI();
    render();
  });

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
// Hidden-titles UI
// ---------------------------------------------------------------------------
function refreshHiddenUI() {
  const map = hiddenTitlesGet();
  const n = Object.keys(map).length;

  if (n === 0) {
    hiddenBtn.classList.add("hidden");
    hiddenBtn.classList.remove("flex");
    hiddenPanel.classList.add("hidden");
    return;
  }

  hiddenBtn.classList.remove("hidden");
  hiddenBtn.classList.add("flex");
  hiddenCount.textContent = `${n} hidden`;

  hiddenPanel.innerHTML = "";

  const header = document.createElement("div");
  header.className = "flex items-center justify-between pb-2 mb-1 border-b border-slate-100";
  const heading = document.createElement("span");
  heading.className = "text-xs font-semibold text-slate-500 uppercase tracking-wide";
  heading.textContent = "Hidden titles";
  const clearAll = document.createElement("button");
  clearAll.className = "text-xs text-rose-500 hover:text-rose-700 underline";
  clearAll.textContent = "Unhide all";
  clearAll.addEventListener("click", () => {
    hiddenTitlesClear();
    refreshHiddenUI();
    render();
  });
  header.appendChild(heading);
  header.appendChild(clearAll);
  hiddenPanel.appendChild(header);

  Object.entries(map).forEach(([norm, display]) => {
    const row = document.createElement("div");
    row.className = "flex items-center gap-2 py-0.5";
    const titleEl = document.createElement("span");
    titleEl.className = "flex-1 text-sm text-slate-700 truncate";
    titleEl.textContent = display;
    titleEl.title = display;
    const undo = document.createElement("button");
    undo.className = "text-xs text-sky-500 hover:text-sky-700 underline shrink-0";
    undo.textContent = "Unhide";
    undo.addEventListener("click", () => {
      hiddenTitleRemove(display);
      refreshHiddenUI();
      render();
    });
    row.appendChild(titleEl);
    row.appendChild(undo);
    hiddenPanel.appendChild(row);
  });
}

hiddenBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  hiddenPanel.classList.toggle("hidden");
});

document.addEventListener("click", (e) => {
  if (!hiddenWrap.contains(e.target)) {
    hiddenPanel.classList.add("hidden");
  }
});

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------
[searchInput, filterDateFrom, filterDateTo].forEach(
  (el) => el.addEventListener("input", render)
);
filterKids.addEventListener("change", render);
filterSaved.addEventListener("change", render);

resetBtn.addEventListener("click", () => {
  searchInput.value     = "";
  filterKids.checked    = false;
  filterSaved.checked   = false;
  filterDateFrom.value  = todayISO();
  filterDateTo.value    = oneMonthISO();
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
filterDateFrom.value = todayISO();
filterDateTo.value   = oneMonthISO();
refreshHiddenUI();
loadEvents();
