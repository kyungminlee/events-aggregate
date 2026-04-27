"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let allEvents = [];

// Local YYYY-MM-DD (not UTC, not locale-dependent). Called fresh each render
// so a tab left open across midnight still highlights the correct "today".
function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// Two-week view state
function getWeekStart(d) {
  const s = new Date(d);
  s.setDate(s.getDate() - s.getDay()); // back to Sunday
  s.setHours(0, 0, 0, 0);
  return s;
}

// Month view state (initial values at load; navigation mutates these)
const _initDate  = new Date();
let currentYear  = _initDate.getFullYear();
let currentMonth = _initDate.getMonth();   // 0-based
let twoWeekStart = getWeekStart(_initDate);

// Shared state
let currentView    = "month";   // "month" | "2week"
let selectedDate   = null;
let selectedSources = new Set(); // empty = "all sources"

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const $ = id => document.getElementById(id);

const loading     = $("loading");
const errorMsg    = $("error-msg");
const errorText   = $("error-text");
const calWrapper  = $("cal-wrapper");
const calGrid     = $("cal-grid");
const calTitle    = $("cal-title");
const dayPanel    = $("day-panel");
const dayTitle    = $("day-title");
const dayEvents   = $("day-events");
const dayNoEvents = $("day-no-events");

const searchInput       = $("search");
const filterKids        = $("filter-kids");
const filterSaved       = $("filter-saved");
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

const viewMonthBtn  = $("view-month");
const view2WeekBtn  = $("view-2week");

// ---------------------------------------------------------------------------
// Source filter dropdown
// ---------------------------------------------------------------------------
function updateSourceLabel() {
  sourceFilterLabel.textContent = selectedSources.size === 0
    ? "All sources"
    : `${selectedSources.size} source${selectedSources.size > 1 ? "s" : ""}`;
}

function buildSourceCheckboxes(sources) {
  sourceFilterPanel.innerHTML = "";
  sources.forEach(src => {
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

sourceFilterBtn.addEventListener("click", e => {
  e.stopPropagation();
  sourceFilterPanel.classList.toggle("hidden");
});

document.addEventListener("click", e => {
  if (!sourceFilterWrap.contains(e.target)) {
    sourceFilterPanel.classList.add("hidden");
  }
});

// ---------------------------------------------------------------------------
// Load events.json
// ---------------------------------------------------------------------------
async function loadEvents() {
  try {
    const res = await fetch("data/events.json?v=" + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allEvents = data.events || [];

    if (data.updated_at) {
      const d = new Date(data.updated_at);
      metaUpdated.textContent = "Updated: " + d.toLocaleDateString("en-US", {
        month: "short", day: "numeric", year: "numeric",
      });
    }
    metaCounts.textContent =
      `${data.total} events · ${data.kids_total} kids/family · ${data.library_total} library`;

    // Build source checkboxes
    const sources = [...new Set(allEvents.map(e => e.source))].sort();
    buildSourceCheckboxes(sources);

    loading.classList.add("hidden");
    calWrapper.classList.remove("hidden");
    render();
  } catch (err) {
    loading.classList.add("hidden");
    errorText.textContent = "Could not load events: " + err.message;
    errorMsg.classList.remove("hidden");
  }
}

// ---------------------------------------------------------------------------
// Filter
// ---------------------------------------------------------------------------
function getFiltered() {
  const q         = searchInput.value.trim().toLowerCase();
  const kidsOnly  = filterKids.checked;
  const savedOnly = filterSaved.checked;

  return allEvents.filter(ev => {
    if (isTitleHidden(ev.title))                                      return false;
    if (kidsOnly && !ev.is_kids_event)                                return false;
    if (savedOnly && !isEventSaved(ev.id))                            return false;
    if (selectedSources.size > 0 && !selectedSources.has(ev.source)) return false;
    if (q) {
      const hay = `${ev.title} ${ev.description || ""} ${ev.source} ${(ev.categories || []).join(" ")}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

// ---------------------------------------------------------------------------
// Main render
// ---------------------------------------------------------------------------
function render() {
  const filtered = getFiltered();
  resultCount.textContent = filtered.length + " event" + (filtered.length !== 1 ? "s" : "");

  if (currentView === "month") {
    renderMonth(filtered);
  } else {
    renderTwoWeek(filtered);
  }

  if (selectedDate) {
    renderDayPanel(selectedDate, filtered.filter(ev => ev.date_start === selectedDate));
  }
}

// ---------------------------------------------------------------------------
// Shared cell builder
// ---------------------------------------------------------------------------
function buildDayCell(dateStr, evs, dayNumber, isToday, maxChips) {
  const isSel = dateStr === selectedDate;

  const cell = document.createElement("div");
  cell.className = [
    "border-r border-b border-slate-200 p-1 cursor-pointer transition-colors relative",
    isToday ? "bg-sky-50"  : "bg-white hover:bg-slate-50",
    isSel   ? "ring-2 ring-inset ring-sky-400" : "",
  ].filter(Boolean).join(" ");
  cell.dataset.date = dateStr;

  // Day number circle
  const dayNum = document.createElement("div");
  dayNum.className = [
    "text-xs font-semibold mb-1 w-6 h-6 flex items-center justify-center rounded-full select-none",
    isToday ? "bg-sky-500 text-white" : "text-slate-500",
  ].join(" ");
  dayNum.textContent = dayNumber;
  cell.appendChild(dayNum);

  // Event chips
  evs.slice(0, maxChips).forEach(ev => {
    const chip = document.createElement("div");
    chip.className = "cal-chip " + (ev.source_type === "library" ? "cal-chip-lib" : "cal-chip-city");
    chip.title = ev.title;
    const txt = document.createElement("span");
    txt.className = "cal-chip-text";
    txt.textContent = ev.title;
    chip.appendChild(txt);
    cell.appendChild(chip);
  });
  if (evs.length > maxChips) {
    const more = document.createElement("div");
    more.className = "text-[10px] text-slate-400 pl-1";
    more.textContent = `+${evs.length - maxChips} more`;
    cell.appendChild(more);
  }

  cell.addEventListener("click", () => {
    selectedDate = dateStr;
    render();
    setTimeout(() => dayPanel.scrollIntoView({ behavior: "smooth", block: "nearest" }), 30);
  });

  return cell;
}

// ---------------------------------------------------------------------------
// Month view
// ---------------------------------------------------------------------------
function renderMonth(filtered) {
  const byDate = {};
  filtered.forEach(ev => {
    (byDate[ev.date_start] = byDate[ev.date_start] || []).push(ev);
  });

  const pad      = n => String(n).padStart(2, "0");
  const today    = todayISO();
  const firstDay = new Date(currentYear, currentMonth, 1).getDay();
  const lastDay  = new Date(currentYear, currentMonth + 1, 0).getDate();
  const monthStr = `${currentYear}-${pad(currentMonth + 1)}`;

  calTitle.textContent = new Date(currentYear, currentMonth, 1)
    .toLocaleDateString("en-US", { month: "long", year: "numeric" });

  calGrid.innerHTML = "";

  // Empty filler cells before the 1st
  for (let i = 0; i < firstDay; i++) {
    const filler = document.createElement("div");
    filler.className = "bg-slate-50 border-r border-b border-slate-200 min-h-[90px]";
    calGrid.appendChild(filler);
  }

  // Day cells
  for (let day = 1; day <= lastDay; day++) {
    const dateStr = `${monthStr}-${pad(day)}`;
    const evs     = byDate[dateStr] || [];
    const cell    = buildDayCell(dateStr, evs, day, dateStr === today, 3);
    cell.style.minHeight = "90px";
    calGrid.appendChild(cell);
  }

  // Trailing filler cells
  const totalCells = firstDay + lastDay;
  const remainder  = totalCells % 7;
  if (remainder !== 0) {
    for (let i = 0; i < 7 - remainder; i++) {
      const filler = document.createElement("div");
      filler.className = "bg-slate-50 border-r border-b border-slate-200 min-h-[90px]";
      calGrid.appendChild(filler);
    }
  }
}

// ---------------------------------------------------------------------------
// Two-week view
// ---------------------------------------------------------------------------
function renderTwoWeek(filtered) {
  const byDate = {};
  filtered.forEach(ev => {
    (byDate[ev.date_start] = byDate[ev.date_start] || []).push(ev);
  });

  const pad   = n => String(n).padStart(2, "0");
  const today = todayISO();

  // Title: "Feb 22 – Mar 7, 2026"
  const endDate = new Date(twoWeekStart);
  endDate.setDate(endDate.getDate() + 13);
  const fmtShort = d => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  calTitle.textContent =
    `${fmtShort(twoWeekStart)} – ${fmtShort(endDate)}, ${endDate.getFullYear()}`;

  calGrid.innerHTML = "";

  for (let i = 0; i < 14; i++) {
    const d = new Date(twoWeekStart);
    d.setDate(d.getDate() + i);
    const dateStr = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const evs     = byDate[dateStr] || [];
    const cell    = buildDayCell(dateStr, evs, d.getDate(), dateStr === today, 8);
    cell.style.minHeight = "180px";
    calGrid.appendChild(cell);
  }
}

// ---------------------------------------------------------------------------
// Day panel
// ---------------------------------------------------------------------------
function renderDayPanel(dateStr, evs) {
  const [y, m, d] = dateStr.split("-").map(Number);
  dayTitle.textContent = new Date(y, m - 1, d).toLocaleDateString("en-US", {
    weekday: "long", month: "long", day: "numeric", year: "numeric",
  });

  dayEvents.innerHTML = "";
  if (!evs.length) {
    dayNoEvents.classList.remove("hidden");
    dayEvents.classList.add("hidden");
  } else {
    dayNoEvents.classList.add("hidden");
    dayEvents.classList.remove("hidden");
    evs.forEach(ev => dayEvents.appendChild(makeCard(ev)));
  }
  dayPanel.classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Event card builder
// ---------------------------------------------------------------------------
function fmtTime(t) {
  const [h, m] = t.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"}`;
}

function makeCard(ev) {
  const card = document.createElement("article");
  card.className = "event-card bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden flex flex-col hover:shadow-md transition-shadow";

  if (ev.image_url) {
    const wrap = document.createElement("div");
    wrap.className = "relative h-36 bg-slate-100 overflow-hidden";
    const img = document.createElement("img");
    img.className = "w-full h-full object-cover";
    img.src = ev.image_url;
    img.alt = ev.title;
    img.loading = "lazy";
    wrap.appendChild(img);
    card.appendChild(wrap);
  }

  const body = document.createElement("div");
  body.className = "p-4 flex flex-col flex-1 gap-2";

  const titleRow = document.createElement("div");
  titleRow.className = "flex items-start justify-between gap-2";
  const title = document.createElement("h2");
  title.className = "font-semibold text-slate-800 text-sm leading-snug line-clamp-2";
  title.textContent = ev.title;
  titleRow.appendChild(title);
  const rightCluster = document.createElement("div");
  rightCluster.className = "flex items-center gap-1 shrink-0";
  if (ev.is_kids_event) {
    const badge = document.createElement("span");
    badge.className = "text-xs px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-700 font-medium";
    badge.textContent = "👧 Kids";
    rightCluster.appendChild(badge);
  }
  const saveBtn = document.createElement("button");
  saveBtn.className = "save-btn text-base leading-none w-5 h-5 flex items-center justify-center rounded transition-colors";
  saveBtn.setAttribute("aria-label", "Save");
  function paintSave() {
    const saved = isEventSaved(ev.id);
    saveBtn.textContent = saved ? "★" : "☆";
    saveBtn.classList.toggle("text-amber-500", saved);
    saveBtn.classList.toggle("text-slate-300", !saved);
    saveBtn.classList.toggle("hover:text-amber-600", saved);
    saveBtn.classList.toggle("hover:text-amber-500", !saved);
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
  rightCluster.appendChild(saveBtn);

  const hideBtn = document.createElement("button");
  hideBtn.className = "text-slate-300 hover:text-rose-500 text-base leading-none w-5 h-5 flex items-center justify-center rounded transition-colors";
  hideBtn.title = "Hide events with this title";
  hideBtn.setAttribute("aria-label", "Hide");
  hideBtn.textContent = "×";
  hideBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    hiddenTitleAdd(ev.title);
    refreshHiddenUI();
    render();
  });
  rightCluster.appendChild(hideBtn);
  titleRow.appendChild(rightCluster);
  body.appendChild(titleRow);

  if (ev.time_start) {
    const timeEl = document.createElement("div");
    timeEl.className = "text-sky-600 text-xs font-medium";
    timeEl.textContent = fmtTime(ev.time_start) + (ev.time_end ? ` – ${fmtTime(ev.time_end)}` : "");
    body.appendChild(timeEl);
  }

  if (ev.location) {
    const loc = document.createElement("div");
    loc.className = "text-slate-500 text-xs truncate";
    loc.textContent = ev.location;
    body.appendChild(loc);
  }

  if (ev.description) {
    const desc = document.createElement("p");
    desc.className = "text-slate-600 text-xs line-clamp-3 flex-1";
    desc.textContent = ev.description;
    body.appendChild(desc);
  }

  const footer = document.createElement("div");
  footer.className = "flex items-center justify-between mt-1";
  const srcBadge = document.createElement("span");
  srcBadge.className = "text-xs px-2 py-0.5 rounded-full font-medium " +
    (ev.source_type === "library" ? "badge-library" : "badge-city");
  srcBadge.textContent = ev.source;
  footer.appendChild(srcBadge);
  const link = document.createElement("a");
  link.className = "text-xs text-sky-500 hover:text-sky-700 font-medium";
  link.href = ev.url;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = "Details →";
  footer.appendChild(link);
  body.appendChild(footer);

  if (ev.categories && ev.categories.length) {
    const cats = document.createElement("div");
    cats.className = "flex flex-wrap gap-1";
    ev.categories.slice(0, 4).forEach(c => {
      const tag = document.createElement("span");
      tag.className = "text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-500";
      tag.textContent = c;
      cats.appendChild(tag);
    });
    body.appendChild(cats);
  }

  card.appendChild(body);
  return card;
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
$("prev-btn").addEventListener("click", () => {
  if (currentView === "month") {
    currentMonth--;
    if (currentMonth < 0) { currentMonth = 11; currentYear--; }
  } else {
    twoWeekStart = new Date(twoWeekStart);
    twoWeekStart.setDate(twoWeekStart.getDate() - 14);
  }
  selectedDate = null;
  dayPanel.classList.add("hidden");
  render();
});

$("next-btn").addEventListener("click", () => {
  if (currentView === "month") {
    currentMonth++;
    if (currentMonth > 11) { currentMonth = 0; currentYear++; }
  } else {
    twoWeekStart = new Date(twoWeekStart);
    twoWeekStart.setDate(twoWeekStart.getDate() + 14);
  }
  selectedDate = null;
  dayPanel.classList.add("hidden");
  render();
});

$("today-btn").addEventListener("click", () => {
  const d = new Date();
  currentYear  = d.getFullYear();
  currentMonth = d.getMonth();
  twoWeekStart = getWeekStart(d);
  selectedDate = null;
  dayPanel.classList.add("hidden");
  render();
});

$("close-panel").addEventListener("click", () => {
  selectedDate = null;
  dayPanel.classList.add("hidden");
  render();
});

// ---------------------------------------------------------------------------
// View toggle
// ---------------------------------------------------------------------------
viewMonthBtn.addEventListener("click", () => {
  if (currentView === "month") return;
  currentView = "month";
  viewMonthBtn.classList.add("active");
  view2WeekBtn.classList.remove("active");
  selectedDate = null;
  dayPanel.classList.add("hidden");
  render();
});

view2WeekBtn.addEventListener("click", () => {
  if (currentView === "2week") return;
  currentView = "2week";
  // Snap two-week window so it includes today or the currently displayed month
  twoWeekStart = getWeekStart(new Date());
  view2WeekBtn.classList.add("active");
  viewMonthBtn.classList.remove("active");
  selectedDate = null;
  dayPanel.classList.add("hidden");
  render();
});

// ---------------------------------------------------------------------------
// Filter listeners
// ---------------------------------------------------------------------------
searchInput.addEventListener("input",  render);
filterKids.addEventListener("change", render);
filterSaved.addEventListener("change", render);

resetBtn.addEventListener("click", () => {
  searchInput.value     = "";
  filterKids.checked    = false;
  filterSaved.checked   = false;
  selectedSources.clear();
  sourceFilterPanel.querySelectorAll("input[type=checkbox]").forEach(cb => { cb.checked = false; });
  updateSourceLabel();
  render();
});

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
// Init
// ---------------------------------------------------------------------------
refreshHiddenUI();
loadEvents();
