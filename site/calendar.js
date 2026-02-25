"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let allEvents = [];
const now = new Date();
let currentYear  = now.getFullYear();
let currentMonth = now.getMonth();   // 0-based
let selectedDate = null;

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const $ = id => document.getElementById(id);

const loading     = $("loading");
const errorMsg    = $("error-msg");
const errorText   = $("error-text");
const calWrapper  = $("cal-wrapper");
const calGrid     = $("cal-grid");
const monthTitle  = $("month-title");
const dayPanel    = $("day-panel");
const dayTitle    = $("day-title");
const dayEvents   = $("day-events");
const dayNoEvents = $("day-no-events");

const searchInput   = $("search");
const filterKids    = $("filter-kids");
const filterLibrary = $("filter-library");
const filterSource  = $("filter-source");
const resetBtn      = $("reset-filters");
const resultCount   = $("result-count");
const metaUpdated   = $("meta-updated");
const metaCounts    = $("meta-counts");

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

    // Populate source dropdown
    const sources = [...new Set(allEvents.map(e => e.source))].sort();
    sources.forEach(src => {
      const opt = document.createElement("option");
      opt.value = src;
      opt.textContent = src;
      filterSource.appendChild(opt);
    });

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
  const q        = searchInput.value.trim().toLowerCase();
  const kidsOnly = filterKids.checked;
  const libOnly  = filterLibrary.checked;
  const srcVal   = filterSource.value;

  return allEvents.filter(ev => {
    if (kidsOnly && !ev.is_kids_event)            return false;
    if (libOnly  && ev.source_type !== "library") return false;
    if (srcVal   && ev.source !== srcVal)         return false;
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
  renderCalendar(filtered);
  if (selectedDate) {
    renderDayPanel(selectedDate, filtered.filter(ev => ev.date_start === selectedDate));
  }
}

// ---------------------------------------------------------------------------
// Calendar grid
// ---------------------------------------------------------------------------
function renderCalendar(filtered) {
  // Group events by date string
  const byDate = {};
  filtered.forEach(ev => {
    (byDate[ev.date_start] = byDate[ev.date_start] || []).push(ev);
  });

  const pad      = n => String(n).padStart(2, "0");
  const today    = now.toISOString().slice(0, 10);
  const firstDay = new Date(currentYear, currentMonth, 1).getDay();   // 0=Sun
  const lastDay  = new Date(currentYear, currentMonth + 1, 0).getDate();
  const monthStr = `${currentYear}-${pad(currentMonth + 1)}`;

  monthTitle.textContent = new Date(currentYear, currentMonth, 1)
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
    const dateStr  = `${monthStr}-${pad(day)}`;
    const evs      = byDate[dateStr] || [];
    const isToday  = dateStr === today;
    const isSel    = dateStr === selectedDate;

    const cell = document.createElement("div");
    cell.className = [
      "border-r border-b border-slate-200 p-1 min-h-[90px] cursor-pointer transition-colors relative",
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
    dayNum.textContent = day;
    cell.appendChild(dayNum);

    // Event chips (up to 3, then "+N more")
    const MAX_CHIPS = 3;
    evs.slice(0, MAX_CHIPS).forEach(ev => {
      const chip = document.createElement("div");
      chip.className = "cal-chip " + (ev.source_type === "library" ? "cal-chip-lib" : "cal-chip-city");
      chip.title = ev.title;
      const txt = document.createElement("span");
      txt.className = "cal-chip-text";
      txt.textContent = ev.title;
      chip.appendChild(txt);
      cell.appendChild(chip);
    });
    if (evs.length > MAX_CHIPS) {
      const more = document.createElement("div");
      more.className = "text-[10px] text-slate-400 pl-1";
      more.textContent = `+${evs.length - MAX_CHIPS} more`;
      cell.appendChild(more);
    }

    cell.addEventListener("click", () => {
      selectedDate = dateStr;
      render();
      setTimeout(() => dayPanel.scrollIntoView({ behavior: "smooth", block: "nearest" }), 30);
    });

    calGrid.appendChild(cell);
  }

  // Fill trailing cells to complete the last row
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
// Day panel
// ---------------------------------------------------------------------------
function renderDayPanel(dateStr, evs) {
  // Parse as local date to avoid off-by-one from UTC
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
// Event card builder (mirrors app.js style)
// ---------------------------------------------------------------------------
function fmtTime(t) {
  const [h, m] = t.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"}`;
}

function makeCard(ev) {
  const card = document.createElement("article");
  card.className = "event-card bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden flex flex-col hover:shadow-md transition-shadow";

  // Optional image
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

  // Title + kids badge
  const titleRow = document.createElement("div");
  titleRow.className = "flex items-start justify-between gap-2";
  const title = document.createElement("h2");
  title.className = "font-semibold text-slate-800 text-sm leading-snug line-clamp-2";
  title.textContent = ev.title;
  titleRow.appendChild(title);
  if (ev.is_kids_event) {
    const badge = document.createElement("span");
    badge.className = "shrink-0 text-xs px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-700 font-medium";
    badge.textContent = "👧 Kids";
    titleRow.appendChild(badge);
  }
  body.appendChild(titleRow);

  // Time
  if (ev.time_start) {
    const timeEl = document.createElement("div");
    timeEl.className = "text-sky-600 text-xs font-medium";
    timeEl.textContent = fmtTime(ev.time_start) + (ev.time_end ? ` – ${fmtTime(ev.time_end)}` : "");
    body.appendChild(timeEl);
  }

  // Location
  if (ev.location) {
    const loc = document.createElement("div");
    loc.className = "text-slate-500 text-xs truncate";
    loc.textContent = ev.location;
    body.appendChild(loc);
  }

  // Description
  if (ev.description) {
    const desc = document.createElement("p");
    desc.className = "text-slate-600 text-xs line-clamp-3 flex-1";
    desc.textContent = ev.description;
    body.appendChild(desc);
  }

  // Footer: source badge + link
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

  // Category tags
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
// Month navigation
// ---------------------------------------------------------------------------
$("prev-month").addEventListener("click", () => {
  currentMonth--;
  if (currentMonth < 0) { currentMonth = 11; currentYear--; }
  selectedDate = null;
  dayPanel.classList.add("hidden");
  render();
});

$("next-month").addEventListener("click", () => {
  currentMonth++;
  if (currentMonth > 11) { currentMonth = 0; currentYear++; }
  selectedDate = null;
  dayPanel.classList.add("hidden");
  render();
});

$("today-btn").addEventListener("click", () => {
  currentYear  = now.getFullYear();
  currentMonth = now.getMonth();
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
// Filter listeners
// ---------------------------------------------------------------------------
searchInput.addEventListener("input",   render);
filterKids.addEventListener("change",   render);
filterLibrary.addEventListener("change", render);
filterSource.addEventListener("change", render);

resetBtn.addEventListener("click", () => {
  searchInput.value    = "";
  filterKids.checked   = true;
  filterLibrary.checked = false;
  filterSource.value   = "";
  render();
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
loadEvents();
