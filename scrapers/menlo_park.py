"""Scraper for City of Menlo Park events.

Source: https://www.menlopark.gov/Citywide-calendar
Platform: Granicus OpenCities

Pagination: The site uses a non-standard query parameter for paging:
  dlv_OC+CL+Public+Events+Listing=(pageindex=N)
  (simple ?page=N is ignored server-side).

HTML structure (verified):
  Cards are bare <a href="/Government/.../Events/..."> elements (no article wrapper).
  Inside each card:
    <img>                           thumbnail
    <h3>Title</h3>
    <p>25 Feb 2026</p>              date (sometimes includes time)
    <p>Description text…</p>
    <p>Location name + address</p>
    <p>N more dates</p>             (optional, recurring events — plain <p>, no CSS class)
    <p>Tagged as: , Category1, Category2</p>

Recurring events: the listing shows only the first date; the detail page lists all
occurrences in a <ul> where each <li> has the form:
  "Thursday, September 04, 2025 | 10:15 AM - 10:45 AM"

We fetch three category passes (children, families, teens) and merge.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from urllib.parse import urljoin

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)

_BASE = "https://www.menlopark.gov"
_EVENTS_PATH = "/Citywide-calendar"
_KIDS_CATEGORIES = ["children", "families", "teens"]


class MenloParkScraper(BaseScraper):
    def __init__(self):
        super().__init__("Menlo Park", "city")

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start, end = self.date_range(days_ahead)
        seen: set[str] = set()
        events: list[Event] = []

        for cat in _KIDS_CATEGORIES:
            for page in range(1, 50):
                page_param = f"dlv_OC+CL+Public+Events+Listing=(pageindex={page})"
                url = f"{_BASE}{_EVENTS_PATH}?{page_param}&category={cat}"
                try:
                    resp = self.get(url)
                    page_items = self._parse_page(resp.text)
                    if not page_items:
                        break

                    for ev, detail_url in page_items:
                        # Expand to all occurrence dates if the card showed "N more dates"
                        if detail_url:
                            occurrences = self._fetch_all_dates(detail_url)
                            if not occurrences:
                                occurrences = [(ev.date_start, ev.time_start)]
                        else:
                            occurrences = [(ev.date_start, ev.time_start)]

                        for date_str, time_str in occurrences:
                            if start.isoformat() <= date_str <= end.isoformat():
                                # Include time in ID key so same-time-of-day repeats get distinct IDs
                                id_key = f"{date_str}T{time_str}" if time_str else date_str
                                new_ev = dataclasses.replace(
                                    ev,
                                    id=make_id("Menlo Park", ev.title, id_key),
                                    date_start=date_str,
                                    time_start=time_str,
                                )
                                if new_ev.id not in seen:
                                    seen.add(new_ev.id)
                                    events.append(new_ev)

                    # Stop paging once all first-occurrence dates are past our window
                    first_dates = [ev.date_start for ev, _ in page_items]
                    if all(d > end.isoformat() for d in first_dates):
                        break

                except Exception as exc:
                    logger.warning(f"[Menlo Park] cat={cat} page={page} failed: {exc}")
                    break

        logger.info(f"[Menlo Park] {len(events)} events fetched")
        return events

    def _fetch_all_dates(self, detail_url: str) -> list[tuple[str, str | None]]:
        """Fetch event detail page; return list of (date_str, time_str) for all occurrences."""
        try:
            resp = self.get(detail_url)
            resp.raise_for_status()
        except Exception as exc:
            logger.debug(f"[Menlo Park] detail page failed {detail_url}: {exc}")
            return []

        soup = self.soup(resp.text)
        results = []

        # Dates are in <ul><li> elements; each li has the form:
        # "Thursday, September 04, 2025 | 10:15 AM - 10:45 AM"
        for li in soup.select("ul li"):
            text = li.get_text(" ", strip=True)
            if not re.search(r"\d{4}", text) or "|" not in text:
                continue
            date_part, time_part = text.split("|", 1)
            try:
                from dateutil import parser as dp
                dt = dp.parse(date_part.strip())
                date_str = dt.strftime("%Y-%m-%d")
                # Take only the start time (before the "-" separator)
                t_start = re.split(r"\s*[-\u2013]\s*", time_part.strip())[0].strip()
                dt_t = dp.parse(t_start)
                time_str: str | None = dt_t.strftime("%H:%M") if (dt_t.hour or dt_t.minute) else None
                results.append((date_str, time_str))
            except Exception:
                pass

        return results

    def _parse_page(self, html: str) -> list[tuple[Event, str | None]]:
        soup = self.soup(html)
        items = []

        # Cards are <a href="…/Events/…"> elements that must contain an <h2>
        for card in soup.select('a[href*="/Events/"]'):
            if not card.select_one("h2"):
                continue
            result = self._parse_card(card)
            if result:
                items.append(result)

        return items

    def _parse_card(self, card) -> tuple[Event, str | None] | None:
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
            ev = self.tag_kids(ev)

            # Detect recurring events: plain <p> with "N more dates" text (no CSS class)
            has_more = any(
                re.search(r"\d+\s+more\s+date", p.get_text(strip=True), re.I)
                for p in card.find_all("p")
            )
            detail_url = url if has_more else None

            return ev, detail_url

        except Exception as exc:
            logger.debug(f"[Menlo Park] parse_card failed: {exc}")
            return None
