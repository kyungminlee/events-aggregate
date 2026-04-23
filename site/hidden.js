"use strict";

// Per-browser hide list for event titles. Shared by app.js (agenda) and calendar.js.
// Stored as a JSON object mapping normalized title -> original-cased display title,
// so the unhide UI can show the user the title as it appeared when they hid it.

const HIDDEN_KEY = "bayareaevents.hiddenTitles";

function normalizeTitle(t) {
  return (t || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function hiddenTitlesGet() {
  try {
    return JSON.parse(localStorage.getItem(HIDDEN_KEY)) || {};
  } catch {
    return {};
  }
}

function hiddenTitlesSave(map) {
  localStorage.setItem(HIDDEN_KEY, JSON.stringify(map));
}

function isTitleHidden(title) {
  return Object.prototype.hasOwnProperty.call(hiddenTitlesGet(), normalizeTitle(title));
}

function hiddenTitleAdd(title) {
  const map = hiddenTitlesGet();
  map[normalizeTitle(title)] = title;
  hiddenTitlesSave(map);
}

function hiddenTitleRemove(title) {
  const map = hiddenTitlesGet();
  delete map[normalizeTitle(title)];
  hiddenTitlesSave(map);
}

function hiddenTitlesClear() {
  hiddenTitlesSave({});
}

function hiddenTitlesCount() {
  return Object.keys(hiddenTitlesGet()).length;
}
