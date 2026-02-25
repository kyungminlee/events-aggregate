"""Shared scraper logic for Granicus OpenCities government sites.

Used by: Palo Alto (paloalto.gov), Menlo Park (menlopark.gov).

OpenCities uses server-side rendering for its events directory / citywide
calendar pages, so requests + BeautifulSoup work without JavaScript.
Pagination is handled by incrementing the ?page=N query parameter.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional
from urllib.parse import urljoin, urlencode, urlparse, parse_qs

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)


class OpenCitiesScraper(BaseScraper):
    """
    Args:
        source_name:     Human-readable city name.
        base_url:        Root URL, e.g. "https://www.paloalto.gov".
        events_path:     Path to the paginated events list (default "/Events-Directory").
        kids_filter:     Dict of query params to pre-filter kids events, e.g.
                         {"category": "children"} or {"audience": "children"}.
        max_pages:       Safety limit on pagination (default 20).
    """

    def __init__(
        self,
        source_name: str,
        base_url: str,
        events_path: str = "/Events-Directory",
        kids_filter: Optional[dict] = None,
        max_pages: int = 20,
    ):
        super().__init__(source_name, "city")
        self.base_url = base_url.rstrip("/")
        self.events_path = events_path
        self.kids_filter = kids_filter or {}
        self.max_pages = max_pages

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start, end = self.date_range(days_ahead)
        events: list[Event] = []
        seen: set[str] = set()

        for page in range(1, self.max_pages + 1):
            params: dict = {"page": page}
            params.update(self.kids_filter)
            # Add date range if site supports it
            params["startDate"] = start.strftime("%m/%d/%Y")
            params["endDate"] = end.strftime("%m/%d/%Y")

            url = f"{self.base_url}{self.events_path}?{urlencode(params)}"
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
                logger.warning(f"[{self.source_name}] page {page} failed: {exc}")
                break

        logger.info(f"[{self.source_name}] {len(events)} events fetched")
        return events

    def _parse_page(self, html: str) -> tuple[list[Event], bool]:
        """Returns (events_on_page, has_next_page)."""
        soup = self.soup(html)
        events = []

        # OpenCities event list — cards vary by theme but share common patterns
        # Try multiple selectors in priority order
        card_selectors = [
            "article.event-item",
            ".event-listing-item",
            ".event-card",
            ".views-row",          # Drupal-style fallback
            "li.event",
        ]
        cards = []
        for sel in card_selectors:
            cards = soup.select(sel)
            if cards:
                break

        # If no specific cards found, try generic article/li items with event links
        if not cards:
            cards = soup.select("article, li")

        for card in cards:
            ev = self._parse_card(card)
            if ev:
                events.append(ev)

        # Detect "next page" link
        next_link = soup.select_one('a[rel="next"], .pagination .next a, a[aria-label="Next"]')
        has_next = next_link is not None and not next_link.get("aria-disabled")

        return events, has_next

    def _parse_card(self, card) -> Optional[Event]:
        try:
            # Title + link
            title_el = card.select_one("h2 a, h3 a, h4 a, .event-title a, .title a")
            if not title_el:
                title_el = card.select_one("a[href*='Event'], a[href*='event']")
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            if not title:
                return None

            href = title_el.get("href", "")
            url = urljoin(self.base_url, href) if href else self.base_url

            # Date / time
            date_str = time_str = time_end = None
            date_el = card.select_one("time, .date, .event-date, .datetime")
            if date_el:
                raw = date_el.get("datetime") or date_el.get_text(" ", strip=True)
                try:
                    from dateutil import parser as dp
                    dt = dp.parse(raw)
                    date_str = dt.strftime("%Y-%m-%d")
                    time_str = dt.strftime("%H:%M") if (dt.hour or dt.minute) else None
                except Exception:
                    pass

            if not date_str:
                # Look for date text in any element
                for el in card.select(".date, .datetime, [class*='date']"):
                    raw = el.get_text(strip=True)
                    if raw:
                        try:
                            from dateutil import parser as dp
                            dt = dp.parse(raw)
                            date_str = dt.strftime("%Y-%m-%d")
                            time_str = dt.strftime("%H:%M") if (dt.hour or dt.minute) else None
                            break
                        except Exception:
                            continue

            if not date_str:
                return None  # Can't place event in time — skip

            # Location
            loc_el = card.select_one(".location, .address, [class*='location']")
            location = loc_el.get_text(strip=True) if loc_el else None

            # Description
            desc_el = card.select_one(".description, .summary, p")
            desc = desc_el.get_text(strip=True)[:500] if desc_el else None

            # Categories
            cats = [el.get_text(strip=True) for el in card.select(".category, .tag, .label")]

            # Image
            img = card.select_one("img")
            image_url = img.get("src") if img else None
            if image_url and not image_url.startswith("http"):
                image_url = urljoin(self.base_url, image_url)

            ev = Event(
                id=make_id(self.source_name, title, date_str),
                title=title,
                url=url,
                source=self.source_name,
                source_type=self.source_type,
                date_start=date_str,
                time_start=time_str,
                location=location,
                description=desc,
                categories=cats,
                image_url=image_url,
            )
            return self.tag_kids(ev)
        except Exception as exc:
            logger.debug(f"[{self.source_name}] parse_card failed: {exc}")
            return None
