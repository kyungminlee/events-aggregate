"""Scraper for City of Sunnyvale events.

Source:   https://www.sunnyvale.ca.gov/news-center-and-events-calendar/city-calendar
Platform: Vision CMS (VisionLive / CivicPlus) — server-rendered calendar grid.
CDN:      Akamai — bypassed via curl-cffi Chrome TLS impersonation in BaseScraper.

The Vision CMS API requires IP allowlisting (returns error 900), so we scrape the
server-rendered calendar grid instead. The grid is rendered month-by-month via path
segments: /-curm-{M}/-cury-{YYYY}/-view-list

HTML structure (one entry per event in the grid):
  <td class="... calendar_day_with_items">
    {day_number}
    <div class="calendar_items">
      <div class="calendar_item">
        <span class="calendar_eventtime">2:00 PM</span>
        <a class="calendar_eventlink"
           href="/Home/Components/Calendar/Event/{id}/19?curm=3&cury=2026&view=list"
           title="Event Title">Event Title</a>
      </div>
    </div>
  </td>

Cells with class "calendar_othermonthday" are adjacent-month filler rows — skipped.

Event detail pages (/Home/Components/Calendar/Event/{id}/19?...) are statically rendered
and provide description and location:
  <div class="detail-content">…description…</div>
  <ul class="detail-list">
    <li><span class="detail-list-label">Location:</span>
        <span class="detail-list-value">Sunnyvale Public Library, 665 W. Olive Ave…</span></li>
  </ul>
"""

from __future__ import annotations

import logging
import re
from datetime import date
from urllib.parse import urljoin

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)

_BASE = "https://www.sunnyvale.ca.gov"
_CAL_PATH = "/news-center-and-events-calendar/city-calendar"


class SunnyvaleScraper(BaseScraper):
    """City of Sunnyvale — Vision CMS calendar grid scraper."""

    def __init__(self):
        super().__init__("City of Sunnyvale", "city")

    # ------------------------------------------------------------------ #
    #  Main fetch                                                          #
    # ------------------------------------------------------------------ #
    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start, end = self.date_range(days_ahead)
        seen: set[str] = set()
        events: list[Event] = []

        # Iterate month-by-month from start to end
        cur_year  = start.year
        cur_month = start.month
        end_year  = end.year
        end_month = end.month

        while (cur_year, cur_month) <= (end_year, end_month):
            url = f"{_BASE}{_CAL_PATH}/-curm-{cur_month}/-cury-{cur_year}/-view-list"
            try:
                resp = self.get(url)
                for ev in self._parse_month(resp.text, cur_year, cur_month):
                    if start <= date.fromisoformat(ev.date_start) <= end:
                        if ev.id not in seen:
                            seen.add(ev.id)
                            events.append(ev)
            except Exception as exc:
                logger.warning(f"[City of Sunnyvale] {cur_year}-{cur_month:02d} failed: {exc}")

            if cur_month == 12:
                cur_year  += 1
                cur_month  = 1
            else:
                cur_month += 1

        # Enrich each event with description + location from its detail page
        for ev in events:
            desc, loc = self._fetch_detail(ev.url)
            ev.description = desc
            ev.location = loc

        logger.info(f"[City of Sunnyvale] {len(events)} events fetched")
        return events

    # ------------------------------------------------------------------ #
    #  Detail page enrichment                                             #
    # ------------------------------------------------------------------ #
    def _fetch_detail(self, url: str) -> tuple[str | None, str | None]:
        """Fetch event detail page; return (description, location)."""
        try:
            resp = self.get(url)
            soup = self.soup(resp.text)

            desc_el = soup.select_one(".detail-content")
            description = desc_el.get_text(strip=True)[:1000] if desc_el else None

            location = None
            for li in soup.select(".detail-list li"):
                label = li.select_one(".detail-list-label")
                value = li.select_one(".detail-list-value")
                if label and value and "location" in label.get_text().lower():
                    raw = value.get_text(separator=", ", strip=True)
                    # Remove artefact double-commas from empty address subfields
                    loc = re.sub(r",\s*,+", ",", raw).strip(", ")
                    location = loc or None
                    break

            return description, location
        except Exception as exc:
            logger.debug(f"[City of Sunnyvale] detail fetch failed {url}: {exc}")
            return None, None

    # ------------------------------------------------------------------ #
    #  HTML parsing                                                        #
    # ------------------------------------------------------------------ #
    def _parse_month(self, html: str, year: int, month: int) -> list[Event]:
        soup = self.soup(html)
        events: list[Event] = []

        for td in soup.select("td.calendar_day_with_items"):
            # Skip filler cells from adjacent months
            if "calendar_othermonthday" in (td.get("class") or []):
                continue

            # Day number: first direct text node inside <td>
            day_str = td.find(string=True, recursive=False)
            if not day_str:
                continue
            try:
                day = int(day_str.strip())
            except ValueError:
                continue

            date_str = f"{year}-{month:02d}-{day:02d}"

            for item in td.select(".calendar_item"):
                ev = self._parse_item(item, date_str)
                if ev:
                    events.append(ev)

        return events

    def _parse_item(self, item, date_str: str) -> Event | None:
        try:
            link = item.select_one("a.calendar_eventlink")
            if not link:
                return None
            title = (link.get("title") or link.get_text(strip=True)).strip()
            if not title:
                return None
            href = link.get("href", "")
            url = urljoin(_BASE, href) if href else _BASE

            time_el = item.select_one("span.calendar_eventtime")
            time_start = self._parse_time(time_el.get_text(strip=True)) if time_el else None

            ev = Event(
                id=make_id(self.source_name, title, date_str),
                title=title,
                url=url,
                source=self.source_name,
                source_type=self.source_type,
                date_start=date_str,
                time_start=time_start,
            )
            return self.tag_kids(ev)
        except Exception as exc:
            logger.debug(f"[City of Sunnyvale] parse_item failed: {exc}")
            return None

    @staticmethod
    def _parse_time(raw: str) -> str | None:
        """Convert '2:00 PM' → '14:00', '11:00 AM' → '11:00'. Returns None if unparseable."""
        m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", raw.strip(), re.I)
        if not m:
            return None
        h, mins, ampm = int(m.group(1)), int(m.group(2)), m.group(3).upper()
        if ampm == "PM" and h != 12:
            h += 12
        elif ampm == "AM" and h == 12:
            h = 0
        return f"{h:02d}:{mins:02d}"
