"use strict";

// Per-browser saved-events list. Shared by app.js (agenda), calendar.js, map.js.
// Stored as a JSON array of stable event IDs (12-char MD5 from scrapers/base.py).
// Hydrated to a Set for O(1) membership checks.

const SAVED_KEY = "bayareaevents.savedEventIds";

function savedEventsGet() {
  try {
    const arr = JSON.parse(localStorage.getItem(SAVED_KEY)) || [];
    return new Set(Array.isArray(arr) ? arr : []);
  } catch {
    return new Set();
  }
}

function savedEventsSave(set) {
  try {
    localStorage.setItem(SAVED_KEY, JSON.stringify([...set]));
  } catch {
    // Quota exceeded or unavailable (private mode) — silently no-op.
  }
}

function isEventSaved(id) {
  return savedEventsGet().has(id);
}

function savedEventAdd(id) {
  const set = savedEventsGet();
  set.add(id);
  savedEventsSave(set);
}

function savedEventRemove(id) {
  const set = savedEventsGet();
  set.delete(id);
  savedEventsSave(set);
}

function savedEventToggle(id) {
  const set = savedEventsGet();
  if (set.has(id)) set.delete(id);
  else set.add(id);
  savedEventsSave(set);
}

function savedEventsCount() {
  return savedEventsGet().size;
}
