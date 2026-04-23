"""Hidden Villa (Los Altos Hills) programs scraper.

Hidden Villa is a working farm and wilderness preserve that runs year-round
public programs — farm tours, Lamb Yoga, Art in the Garden, farm/garden
volunteer days, plus seasonal festivals. Registration is powered by Arlo,
but the public WordPress site at hiddenvilla.org/programs/upcoming/ already
renders each upcoming occurrence with a complete Schema.org Event JSON-LD
block, so no Arlo API calls are needed.

Each <script type="application/ld+json"> block on the page is one event
occurrence and contains name, startDate (ISO with tz offset), endDate,
description, url, and a Place location with street address.

Pagination: WordPress /page/N/ style, ~20 events per page, typically 4
pages of upcoming programs.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Optional

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)

_BASE = "https://www.hiddenvilla.org"
_EVENTS_PATH = "/programs/upcoming/"

# "Day Parking Pass" is sold as a per-day product on the same calendar, not
# programmed content — skip it.
_TITLE_BLOCKLIST = {"day parking pass"}


class HiddenVillaScraper(BaseScraper):
    """Hidden Villa programs via WordPress JSON-LD."""

    def __init__(self):
        super().__init__("Hidden Villa", "venue")

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start, end = self.date_range(days_ahead)
        start_iso, end_iso = start.isoformat(), end.isoformat()
        events: list[Event] = []
        seen: set[str] = set()

        for page in range(1, 20):
            url = (
                f"{_BASE}{_EVENTS_PATH}"
                if page == 1
                else f"{_BASE}{_EVENTS_PATH}page/{page}/"
            )
            try:
                resp = self.get(url)
            except Exception as exc:
                logger.warning(f"[{self.source_name}] page {page} failed: {exc}")
                break

            page_events = self._parse_page(resp.text)
            if not page_events:
                break

            in_window = False
            for ev in page_events:
                if ev.date_start < start_iso or ev.date_start > end_iso:
                    continue
                in_window = True
                if ev.id in seen:
                    continue
                seen.add(ev.id)
                events.append(ev)

            # Pages are ordered earliest-first; stop once the whole page is
            # past our window.
            page_starts = [ev.date_start for ev in page_events]
            if page_starts and min(page_starts) > end_iso:
                break

        logger.info(f"[{self.source_name}] {len(events)} events fetched")
        return events

    def _parse_page(self, html: str) -> list[Event]:
        soup = self.soup(html)
        events: list[Event] = []
        for script in soup.select('script[type="application/ld+json"]'):
            raw = (script.string or "").strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or data.get("@type") != "Event":
                continue
            ev = self._build_event(data)
            if ev:
                events.append(ev)
        return events

    def _build_event(self, data: dict) -> Optional[Event]:
        try:
            title = (data.get("name") or "").strip()
            start_raw = data.get("startDate") or ""
            if not title or not start_raw:
                return None
            if title.lower() in _TITLE_BLOCKLIST:
                return None

            date_start, time_start = _split_iso(start_raw)
            if not date_start:
                return None

            date_end = time_end = None
            end_raw = data.get("endDate") or ""
            if end_raw:
                d_end, t_end = _split_iso(end_raw)
                if d_end and d_end != date_start:
                    date_end = d_end
                time_end = t_end

            url = (data.get("url") or f"{_BASE}{_EVENTS_PATH}").strip()
            desc = _clean(data.get("description"))
            location = _format_location(data.get("location"))
            image_url = None
            img = data.get("image")
            if isinstance(img, str):
                image_url = img
            elif isinstance(img, dict):
                image_url = img.get("url")

            id_key = f"{date_start}T{time_start}" if time_start else date_start
            ev = Event(
                id=make_id(self.source_name, title, id_key),
                title=title,
                url=url,
                source=self.source_name,
                source_type=self.source_type,
                date_start=date_start,
                date_end=date_end,
                time_start=time_start,
                time_end=time_end,
                location=location,
                description=desc,
                image_url=image_url,
            )
            return self.tag_kids(ev)
        except Exception as exc:
            logger.debug(f"[{self.source_name}] _build_event failed: {exc}")
            return None


def _split_iso(iso: str) -> tuple[Optional[str], Optional[str]]:
    """Return (YYYY-MM-DD, HH:MM) for an ISO datetime with optional tz suffix."""
    iso = iso.strip()
    if not iso:
        return None, None
    # Normalize "-0700" → "-07:00" for fromisoformat on older Pythons.
    iso = re.sub(r"([+-])(\d{2})(\d{2})$", r"\1\2:\3", iso)
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None, None
    date_str = dt.date().isoformat()
    time_str = dt.strftime("%H:%M") if (dt.hour or dt.minute) else None
    return date_str, time_str


def _clean(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed[:500] or None


def _format_location(loc) -> Optional[str]:
    if not loc:
        return None
    if isinstance(loc, list):
        loc = loc[0] if loc else None
        if not loc:
            return None
    if isinstance(loc, str):
        return loc.strip() or None
    if isinstance(loc, dict):
        name = loc.get("name")
        addr = loc.get("address")
        addr_str = None
        if isinstance(addr, dict):
            parts = [
                addr.get("streetAddress"),
                addr.get("addressLocality"),
            ]
            addr_str = ", ".join(p for p in parts if p) or None
        elif isinstance(addr, str):
            addr_str = addr
        if name and addr_str and name not in addr_str:
            return f"{name} — {addr_str}"
        return name or addr_str
    return None
