"""Shared scraper logic for CivicPlus / CivicEngage government sites.

Used by: San Jose (sanjoseca.gov), Mountain View (mountainview.gov).

CivicPlus calendar pages are Angular SPAs. We first try a JSON API endpoint
that some instances expose, then fall back to scraping the server-rendered
"list view" HTML which works without JavaScript for simpler queries.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)


class CivicPlusScraper(BaseScraper):
    """
    Args:
        source_name:  Human-readable city name ("San Jose").
        base_url:     Root URL, e.g. "https://www.sanjoseca.gov".
        calendar_path: Path to the calendar page (default "/news-stories/city-calendar").
        calendar_ids: Optional list of calendar IDs for filtered API queries.
        kids_category: Optional category name/ID to pre-filter kids events via URL param.
    """

    def __init__(
        self,
        source_name: str,
        base_url: str,
        calendar_path: str = "/news-stories/city-calendar",
        calendar_ids: Optional[list[str]] = None,
        kids_category: Optional[str] = None,
    ):
        super().__init__(source_name, "city")
        self.base_url = base_url.rstrip("/")
        self.calendar_path = calendar_path
        self.calendar_ids = calendar_ids or []
        self.kids_category = kids_category

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start, end = self.date_range(days_ahead)
        events: list[Event] = []

        # Strategy 1: JSON API (fastest, cleanest)
        try:
            events = self._fetch_via_api(start, end)
            if events:
                logger.info(f"[{self.source_name}] {len(events)} events via API")
                return events
        except Exception as exc:
            logger.debug(f"[{self.source_name}] API attempt failed: {exc}")

        # Strategy 2: HTML list view, month by month
        try:
            events = self._fetch_via_html(start, end)
            logger.info(f"[{self.source_name}] {len(events)} events via HTML")
        except Exception as exc:
            logger.error(f"[{self.source_name}] HTML scrape failed: {exc}")

        return events

    # ------------------------------------------------------------------ #
    #  Strategy 1 – JSON API                                              #
    # ------------------------------------------------------------------ #
    def _fetch_via_api(self, start: date, end: date) -> list[Event]:
        """
        CivicPlus API endpoint (not all instances expose this).
        Endpoint: {base_url}/api/cms/EventsV2/GetCalendarEvents
        """
        start_ms = int(time.mktime(datetime(start.year, start.month, start.day).timetuple())) * 1000
        end_ms   = int(time.mktime(datetime(end.year,   end.month,   end.day).timetuple())) * 1000

        url = f"{self.base_url}/api/cms/EventsV2/GetCalendarEvents"
        params: dict = {"start": start_ms, "end": end_ms}
        if self.calendar_ids:
            params["calIds"] = ",".join(self.calendar_ids)

        data = self.get_json(url, params=params)
        if not isinstance(data, list):
            data = data.get("data", data.get("events", []))

        events = []
        for item in data:
            ev = self._parse_api_item(item)
            if ev:
                events.append(self.tag_kids(ev))
        return events

    def _parse_api_item(self, item: dict) -> Optional[Event]:
        try:
            title = (item.get("Title") or item.get("title") or "").strip()
            if not title:
                return None

            raw_start = item.get("StartDateTime") or item.get("Start") or item.get("startDate", "")
            from dateutil import parser as dp
            dt = dp.parse(raw_start)
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M") if (dt.hour or dt.minute) else None

            raw_end = item.get("EndDateTime") or item.get("End") or item.get("endDate")
            date_end = time_end = None
            if raw_end:
                dt_end = dp.parse(raw_end)
                date_end = dt_end.strftime("%Y-%m-%d")
                time_end = dt_end.strftime("%H:%M") if (dt_end.hour or dt_end.minute) else None

            event_id = item.get("ItemId") or item.get("Id") or item.get("id", "")
            url = (
                item.get("Url")
                or item.get("url")
                or f"{self.base_url}/Home/Components/Calendar/Event/{event_id}/19"
            )
            if url and not url.startswith("http"):
                url = urljoin(self.base_url, url)

            cats = item.get("CategoryNames") or item.get("categories") or []
            if isinstance(cats, str):
                cats = [cats]

            return Event(
                id=make_id(self.source_name, title, date_str),
                title=title,
                url=url,
                source=self.source_name,
                source_type=self.source_type,
                date_start=date_str,
                date_end=date_end,
                time_start=time_str,
                time_end=time_end,
                description=(item.get("ShortDescription") or item.get("Description") or "")[:500],
                categories=cats,
                location=item.get("Location") or item.get("location") or "",
                image_url=item.get("ImageUrl") or item.get("imageUrl"),
            )
        except Exception as exc:
            logger.debug(f"[{self.source_name}] parse_api_item failed: {exc}")
            return None

    # ------------------------------------------------------------------ #
    #  Strategy 2 – HTML list view                                        #
    # ------------------------------------------------------------------ #
    def _fetch_via_html(self, start: date, end: date) -> list[Event]:
        events: list[Event] = []
        seen: set[str] = set()

        current = date(start.year, start.month, 1)
        while current <= end:
            url = (
                f"{self.base_url}/Home/Components/Calendar/"
                f"?year={current.year}&month={current.month}&day=1&mode=1"
            )
            if self.calendar_ids:
                url += f"&calID={','.join(self.calendar_ids)}"
            if self.kids_category:
                url += f"&catId={self.kids_category}"

            try:
                resp = self.get(url)
                for ev in self._parse_html(resp.text):
                    if ev.id not in seen:
                        seen.add(ev.id)
                        events.append(ev)
            except Exception as exc:
                logger.warning(
                    f"[{self.source_name}] month {current.year}-{current.month:02d} failed: {exc}"
                )

            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

        return events

    def _parse_html(self, html: str) -> list[Event]:
        soup = self.soup(html)
        events = []

        # CivicEngage list-view items appear as <li class="cat_*"> or inside .eventModule
        selectors = [
            ".calendar-item",
            ".eventModule",
            "li[class^='cat_']",
            ".fc-event",      # FullCalendar fallback
        ]
        items = []
        for sel in selectors:
            items = soup.select(sel)
            if items:
                break

        for item in items:
            try:
                a_tag = item.select_one("a[href*='Calendar/Event']") or item.select_one("h2 a, h3 a, .title a")
                if not a_tag:
                    continue
                title = a_tag.get_text(strip=True)
                href = a_tag.get("href", "")
                url = urljoin(self.base_url, href) if href else self.base_url

                date_el = item.select_one(".date, .datetime, time, .eventDate")
                date_str = ""
                if date_el:
                    try:
                        from dateutil import parser as dp
                        dt = dp.parse(date_el.get("datetime") or date_el.get_text(strip=True))
                        date_str = dt.strftime("%Y-%m-%d")
                        time_str = dt.strftime("%H:%M") if (dt.hour or dt.minute) else None
                    except Exception:
                        date_str = ""
                        time_str = None
                else:
                    time_str = None

                if not date_str:
                    continue  # skip items without parseable date

                desc_el = item.select_one(".description, .summary, p")
                desc = desc_el.get_text(strip=True)[:500] if desc_el else ""

                ev = Event(
                    id=make_id(self.source_name, title, date_str),
                    title=title,
                    url=url,
                    source=self.source_name,
                    source_type=self.source_type,
                    date_start=date_str,
                    time_start=time_str,
                    description=desc,
                )
                events.append(self.tag_kids(ev))
            except Exception as exc:
                logger.debug(f"[{self.source_name}] parse HTML item failed: {exc}")

        return events
