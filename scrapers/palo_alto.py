"""Scraper for City of Palo Alto events.

Source:   https://www.paloalto.gov/Events-Directory
Platform: Granicus OpenCities (server-side rendered ASP.NET)
CDN:      Akamai — bypassed via curl-cffi Chrome TLS impersonation in BaseScraper.

Pagination: Same non-standard format as Menlo Park:
  dlv_OC+CL+Public+Events+Listing=(pageindex=N)
  (simple ?page=N is ignored server-side).

HTML structure:
  <article>
    <a href="https://www.paloalto.gov/Events-Directory/{category}/{slug}">
      <h2 class="list-item-title">Title</h2>
      <p class="oc-thumbnail-image"><img src="..."/></p>
      <p class="clearfix">
        <span class="list-item-block-date">
          <span class="part-date">01</span>
          <span class="part-month">Mar</span>
          <span class="part-year">2026</span>
        </span>
        <span class="list-item-block-desc">Description…</span>
      </p>
      <p class="list-item-address">Location address</p>   <!-- optional -->
      <p class="published-on small-text">N more dates</p>  <!-- recurring events -->
      <p class="tagged-as-list">…category tags…</p>
    </a>
  </article>

Recurring events: the listing shows only the first date; the detail page lists all
occurrences in a <ul> where each <li> has the form:
  "Saturday, March 28, 2026 | 10:00 AM - 11:00 AM"
"""

from __future__ import annotations

import dataclasses
import logging
import re
from typing import Optional
from urllib.parse import urljoin

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)

_BASE = "https://www.paloalto.gov"
_EVENTS_PATH = "/Events-Directory"


class PaloAltoScraper(BaseScraper):
    """City of Palo Alto events — uses curl-cffi to bypass Akamai CDN block."""

    def __init__(self):
        super().__init__("City of Palo Alto", "city")

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start, end = self.date_range(days_ahead)
        seen: set[str] = set()
        events: list[Event] = []

        for page in range(1, 20):
            page_param = f"dlv_OC+CL+Public+Events+Listing=(pageindex={page})"
            url = f"{_BASE}{_EVENTS_PATH}?{page_param}"
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
                            # Detail page failed — fall back to first date from listing
                            occurrences = [(ev.date_start, ev.time_start)]
                    else:
                        occurrences = [(ev.date_start, ev.time_start)]

                    for date_str, time_str in occurrences:
                        if start.isoformat() <= date_str <= end.isoformat():
                            # Include time in ID key so same-day performances get distinct IDs
                            id_key = f"{date_str}T{time_str}" if time_str else date_str
                            new_ev = dataclasses.replace(
                                ev,
                                id=make_id("City of Palo Alto", ev.title, id_key),
                                date_start=date_str,
                                time_start=time_str,
                            )
                            if new_ev.id not in seen:
                                seen.add(new_ev.id)
                                events.append(new_ev)

                # Stop paging when all first-occurrence dates are past the window
                first_dates = [ev.date_start for ev, _ in page_items]
                if all(d > end.isoformat() for d in first_dates):
                    break

            except Exception as exc:
                logger.warning(f"[Palo Alto] page {page} failed: {exc}")
                break

        logger.info(f"[Palo Alto] {len(events)} events fetched")
        return events

    def _fetch_all_dates(self, detail_url: str) -> list[tuple[str, str | None]]:
        """Fetch event detail page; return list of (date_str, time_str) for all occurrences."""
        try:
            resp = self.get(detail_url)
        except Exception as exc:
            logger.debug(f"[Palo Alto] detail page failed {detail_url}: {exc}")
            return []

        soup = self.soup(resp.text)
        results = []

        # Dates are in <ul><li> elements; each li has the form:
        # "Saturday, March 28, 2026 | 10:00 AM - 11:00 AM"
        for li in soup.select("ul li"):
            text = li.get_text(" ", strip=True)
            if not re.search(r"\d{4}", text) or "|" not in text:
                continue
            date_part, time_part = text.split("|", 1)
            try:
                from dateutil import parser as dp
                dt = dp.parse(date_part.strip())
                date_str = dt.strftime("%Y-%m-%d")
                # Time range may be "10:00 AM - 11:00 AM" or "10:00 AM \n\t- 11:00 AM"
                # Take only the start time (everything before the "-" separator)
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
        for article in soup.select("article"):
            result = self._parse_card(article)
            if result:
                items.append(result)
        return items

    def _parse_card(self, card) -> Optional[tuple[Event, str | None]]:
        try:
            link = card.select_one("a[href]")
            if not link:
                return None
            url = link.get("href", "")
            if not url.startswith("http"):
                url = urljoin(_BASE, url)

            title_el = card.select_one("h2.list-item-title")
            if not title_el:
                return None
            title = title_el.get_text(strip=True)
            if not title:
                return None

            # Date: day/month/year spans inside .list-item-block-date
            date_el = card.select_one(".list-item-block-date")
            if not date_el:
                return None
            raw_date = date_el.get_text(" ", strip=True)  # "01 Mar 2026"
            try:
                from dateutil import parser as dp
                dt = dp.parse(raw_date, dayfirst=True)
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                return None

            # Description
            desc_el = card.select_one(".list-item-block-desc")
            description = desc_el.get_text(strip=True)[:500] if desc_el else None

            # Location
            loc_el = card.select_one(".list-item-address")
            location = loc_el.get_text(strip=True) if loc_el else None

            # Categories — strip separator spans, split on comma
            categories: list[str] = []
            tags_el = card.select_one(".tagged-as-list")
            if tags_el:
                # Remove "Tagged as:" label and separator spans
                for sep in tags_el.select(".label, .separator"):
                    sep.decompose()
                raw = tags_el.get_text(",", strip=True)
                categories = [c.strip() for c in raw.split(",") if c.strip()]

            # Image
            img = card.select_one(".oc-thumbnail-image img, img")
            image_url = None
            if img:
                src = img.get("src", "")
                if src:
                    image_url = src if src.startswith("http") else urljoin(_BASE, src)

            ev = Event(
                id=make_id("City of Palo Alto", title, date_str),
                title=title,
                url=url,
                source=self.source_name,
                source_type="city",
                date_start=date_str,
                time_start=None,
                location=location,
                description=description,
                categories=categories,
                image_url=image_url,
            )
            ev = self.tag_kids(ev)

            # Detect recurring events: "N more dates" paragraph
            more_dates_el = card.select_one("p.published-on")
            has_more = False
            if more_dates_el:
                text = more_dates_el.get_text(strip=True)
                has_more = bool(re.search(r"\d+\s+more\s+date", text, re.I))
            detail_url = url if has_more else None

            return ev, detail_url

        except Exception as exc:
            logger.debug(f"[Palo Alto] parse_card failed: {exc}")
            return None
