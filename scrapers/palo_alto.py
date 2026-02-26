"""Scraper for City of Palo Alto events.

Source:   https://www.paloalto.gov/Events-Directory
Platform: Granicus OpenCities (server-side rendered ASP.NET)
CDN:      Akamai — blocks Python requests; requires curl-cffi for Chrome TLS impersonation.

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
      <p class="tagged-as-list">…category tags…</p>
    </a>
  </article>
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urljoin

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)

_BASE = "https://www.paloalto.gov"
_EVENTS_PATH = "/Events-Directory"


class PaloAltoScraper(BaseScraper):
    """City of Palo Alto events — uses curl-cffi to bypass Akamai CDN block."""

    def __init__(self):
        super().__init__("Palo Alto", "city")

    def _cffi_get(self, url: str, **kwargs):
        """HTTP GET using curl-cffi with Chrome TLS impersonation."""
        try:
            from curl_cffi import requests as cffi_requests
            return cffi_requests.get(url, impersonate="chrome120", timeout=20, **kwargs)
        except ImportError:
            logger.warning("[Palo Alto] curl-cffi not installed; falling back to requests (likely 403)")
            return self.get(url, **kwargs)

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start, end = self.date_range(days_ahead)
        seen: set[str] = set()
        events: list[Event] = []

        for page in range(1, 20):
            page_param = f"dlv_OC+CL+Public+Events+Listing=(pageindex={page})"
            url = f"{_BASE}{_EVENTS_PATH}?{page_param}"
            try:
                resp = self._cffi_get(url)
                resp.raise_for_status()
                page_events = self._parse_page(resp.text)
                if not page_events:
                    break
                for ev in page_events:
                    if ev.id not in seen and start.isoformat() <= ev.date_start <= end.isoformat():
                        seen.add(ev.id)
                        events.append(ev)
                if all(ev.date_start > end.isoformat() for ev in page_events):
                    break
            except Exception as exc:
                logger.warning(f"[Palo Alto] page {page} failed: {exc}")
                break

        logger.info(f"[Palo Alto] {len(events)} events fetched")
        return events

    def _parse_page(self, html: str) -> list[Event]:
        soup = self.soup(html)
        events = []
        for article in soup.select("article"):
            ev = self._parse_card(article)
            if ev:
                events.append(ev)
        return events

    def _parse_card(self, card) -> Optional[Event]:
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
                id=make_id("Palo Alto", title, date_str),
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
            return self.tag_kids(ev)
        except Exception as exc:
            logger.debug(f"[Palo Alto] parse_card failed: {exc}")
            return None
