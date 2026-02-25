"""Scraper for City of Menlo Park events.

Source: https://www.menlopark.gov/Citywide-calendar
Platform: Granicus OpenCities

HTML structure (verified):
  Cards are bare <a href="/Government/.../Events/..."> elements (no article wrapper).
  Inside each card:
    <img>                           thumbnail
    <h3>Title</h3>
    <p>25 Feb 2026</p>              date (sometimes includes time)
    <p>Description text…</p>
    <p>Location name + address</p>
    <p>N more dates</p>             (optional, recurring events)
    <p>Tagged as: , Category1, Category2</p>

We fetch three category passes (children, families, teens) and merge.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlencode

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)

_BASE = "https://www.menlopark.gov"
_EVENTS_PATH = "/Citywide-calendar"
_KIDS_CATEGORIES = ["children", "families", "teens"]
_ADDR_WORDS = ("Library", "Ave", "St.", "Blvd", "Dr.", "Rd.", "Room",
               "Center", "Campus", "Menlo Park", "Atherton", "Terminal")


class MenloParkScraper(BaseScraper):
    def __init__(self):
        super().__init__("Menlo Park", "city")

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start, end = self.date_range(days_ahead)
        seen: set[str] = set()
        events: list[Event] = []

        for cat in _KIDS_CATEGORIES:
            for page in range(1, 25):
                params = {
                    "page": page,
                    "category": cat,
                    "startDate": start.strftime("%m/%d/%Y"),
                    "endDate": end.strftime("%m/%d/%Y"),
                }
                url = f"{_BASE}{_EVENTS_PATH}?{urlencode(params)}"
                try:
                    resp = self.get(url)
                    page_events, has_next = self._parse_page(resp.text)
                    for ev in page_events:
                        if ev.id not in seen:
                            seen.add(ev.id)
                            events.append(ev)
                    if not has_next:
                        break
                except Exception as exc:
                    logger.warning(f"[Menlo Park] cat={cat} page={page} failed: {exc}")
                    break

        logger.info(f"[Menlo Park] {len(events)} events fetched")
        return events

    def _parse_page(self, html: str) -> tuple[list[Event], bool]:
        soup = self.soup(html)
        events = []

        # Cards are <a href="…/Events/…"> elements that must contain an <h2>
        for card in soup.select('a[href*="/Events/"]'):
            if not card.select_one("h2"):
                continue
            ev = self._parse_card(card)
            if ev:
                events.append(ev)

        next_link = soup.select_one('a[rel="next"], [aria-label="Next page"]')
        has_next = next_link is not None and next_link.get("aria-disabled") != "true"
        return events, has_next

    def _parse_card(self, card) -> Event | None:
        try:
            title_el = card.select_one("h2.list-item-title, h2")
            if not title_el:
                return None
            title = title_el.get_text(strip=True)
            if not title:
                return None

            href = card.get("href", "")
            url = urljoin(_BASE, href) if href else _BASE

            # Date: <span class="list-item-block-date"> with day/month/year sub-spans
            date_str = time_str = None
            date_el = card.select_one(".list-item-block-date")
            if date_el:
                raw_date = date_el.get_text(" ", strip=True)  # "25 Feb 2026"
                try:
                    from dateutil import parser as dp
                    dt = dp.parse(raw_date, dayfirst=True)
                    date_str = dt.strftime("%Y-%m-%d")
                    time_str = dt.strftime("%H:%M") if (dt.hour or dt.minute) else None
                except Exception:
                    pass

            if not date_str:
                return None

            # Description: <span class="list-item-block-desc">
            description = None
            desc_el = card.select_one(".list-item-block-desc")
            if desc_el:
                description = desc_el.get_text(strip=True)[:500]

            # Location: <p class="list-item-address">
            location = None
            loc_el = card.select_one(".list-item-address, p.list-item-address")
            if loc_el:
                location = loc_el.get_text(strip=True)

            # Categories: <p class="tagged-as-list">
            categories: list[str] = []
            tags_el = card.select_one(".tagged-as-list")
            if tags_el:
                raw = tags_el.get_text(strip=True).replace("Tagged as:", "").strip()
                categories = [c.strip() for c in raw.split(",") if c.strip()]

            # Image: inside <p class="oc-thumbnail-image">
            image_url = None
            img = card.select_one(".oc-thumbnail-image img, img")
            if img:
                src = img.get("src", "")
                if src:
                    image_url = src if src.startswith("http") else urljoin(_BASE, src)

            ev = Event(
                id=make_id("Menlo Park", title, date_str),
                title=title,
                url=url,
                source=self.source_name,
                source_type=self.source_type,
                date_start=date_str,
                time_start=time_str,
                location=location,
                description=description,
                categories=categories,
                image_url=image_url,
            )
            return self.tag_kids(ev)
        except Exception as exc:
            logger.debug(f"[Menlo Park] parse_card failed: {exc}")
            return None
