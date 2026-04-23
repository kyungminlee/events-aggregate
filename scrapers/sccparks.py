"""Santa Clara County Parks events scraper.

Source: https://parks.santaclaracounty.gov/events
Platform: Drupal 10 (Views block, no public iCal/RSS/JSONAPI feed)

Page layout (single views block, paginated via ?page=N):

    <h2>Wednesday, April 22, 2026</h2>
    <div class="event-results">
      <a class="event-card" href="/event-slug">
        <h3 class="event-card-title">Wednesday Workday at Martial Cottle Park</h3>
        <div class="event-card-info">
          10:00AM - 12:00PM | In-person EVENT | Martial Cottle Park | San José
        </div>
        <div class="event-card-desc">...</div>
      </a>
    </div>
    <h2>Saturday, April 25, 2026</h2>
    ...

Each h2 is the date header for all .event-results blocks that follow it until
the next h2. Event cards themselves carry only time, not date — we have to
track the most recent h2 while walking the DOM in document order.

Pagination: simple `?page=N` until a page returns zero event-results.
The main calendar runs 2 pages (~50 events) at any given time.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional
from urllib.parse import urljoin

from dateutil import parser as dateparser

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)

_BASE = "https://parks.santaclaracounty.gov"
_EVENTS_PATH = "/events"

# "10:00AM - 12:00PM" or "10:00AM" (no end time)
_TIME_RE = re.compile(
    r"(\d{1,2}:\d{2}\s*[AP]M)(?:\s*-\s*(\d{1,2}:\d{2}\s*[AP]M))?",
    re.IGNORECASE,
)


class SCCParksScraper(BaseScraper):
    """Santa Clara County Parks event calendar."""

    def __init__(self):
        super().__init__("Santa Clara County Parks", "venue")

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start, end = self.date_range(days_ahead)
        start_iso, end_iso = start.isoformat(), end.isoformat()
        events: list[Event] = []
        seen: set[str] = set()

        for page in range(0, 20):
            url = f"{_BASE}{_EVENTS_PATH}?page={page}"
            try:
                resp = self.get(url)
            except Exception as exc:
                logger.warning(f"[{self.source_name}] page {page} failed: {exc}")
                break

            page_events = self._parse_page(resp.text)
            if not page_events:
                break

            in_range = 0
            for ev in page_events:
                if ev.date_start < start_iso or ev.date_start > end_iso:
                    continue
                if ev.id in seen:
                    continue
                seen.add(ev.id)
                events.append(ev)
                in_range += 1

            # Pages are chronological; if every event on this page is past the
            # window, further pages are also past it — but the site sometimes
            # interleaves recurring series so don't hard-stop on in_range=0.

        logger.info(f"[{self.source_name}] {len(events)} events fetched")
        return events

    def _parse_page(self, html: str) -> list[Event]:
        soup = self.soup(html)
        # Scope to the events views block so we don't pick up stray h2s.
        block = soup.select_one(".block-views-blockevent-list-block-1") or soup

        # Walk the DOM in document order. Each h2 date header applies to the
        # event cards that follow it until the next h2. lxml/BeautifulSoup
        # don't preserve sourceline on this HTML, so we traverse descendants
        # directly instead of sorting by line number.
        events: list[Event] = []
        current_date_str: Optional[str] = None
        for el in block.descendants:
            name = getattr(el, "name", None)
            if name == "h2":
                txt = el.get_text(strip=True)
                if "," in txt and any(ch.isdigit() for ch in txt):
                    current_date_str = _parse_date(txt)
            elif name == "a" and "event-card" in (el.get("class") or []):
                if current_date_str:
                    ev = self._parse_card(el, current_date_str)
                    if ev:
                        events.append(ev)
        return events

    def _parse_card(self, card, date_str: str) -> Optional[Event]:
        try:
            title_el = card.select_one(".event-card-title")
            if not title_el:
                return None
            title = title_el.get_text(strip=True)
            if not title:
                return None

            href = card.get("href") or ""
            url = urljoin(_BASE, href) if href else _BASE

            info_el = card.select_one(".event-card-info")
            time_start = time_end = None
            location: Optional[str] = None
            if info_el:
                # Layout is: "{time_range} | In-person EVENT<br>{Park} | {City}"
                # Split on <br> so the time line stays separate from the location line.
                parts = re.split(r"<br\s*/?>", info_el.decode_contents())
                time_text = _strip_tags(parts[0]) if parts else ""
                time_start, time_end = _parse_time_range(time_text)
                loc_text = _strip_tags(parts[1]) if len(parts) > 1 else ""
                # Drop any stray "|" separator after the event-type label.
                loc_text = loc_text.strip().strip("|").strip()
                location = re.sub(r"\s*\|\s*", ", ", loc_text) or None

            desc_el = card.select_one(".event-card-desc")
            desc = desc_el.get_text(strip=True)[:500] if desc_el else None

            id_key = f"{date_str}T{time_start}" if time_start else date_str
            ev = Event(
                id=make_id(self.source_name, title, id_key),
                title=title,
                url=url,
                source=self.source_name,
                source_type=self.source_type,
                date_start=date_str,
                time_start=time_start,
                time_end=time_end,
                location=location,
                description=desc,
            )
            return self.tag_kids(ev)
        except Exception as exc:
            logger.debug(f"[{self.source_name}] _parse_card failed: {exc}")
            return None


def _parse_date(text: str) -> Optional[str]:
    """Parse 'Wednesday, April 22, 2026' → '2026-04-22'."""
    try:
        return dateparser.parse(text).date().isoformat()
    except Exception:
        return None


def _parse_time_range(text: str) -> tuple[Optional[str], Optional[str]]:
    m = _TIME_RE.search(text)
    if not m:
        return None, None
    start = _to_hhmm(m.group(1))
    end = _to_hhmm(m.group(2)) if m.group(2) else None
    return start, end


def _to_hhmm(raw: str) -> Optional[str]:
    try:
        return dateparser.parse(raw).strftime("%H:%M")
    except Exception:
        return None


def _strip_tags(html: str) -> str:
    """Collapse whitespace in an HTML fragment and drop any nested tags."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()
