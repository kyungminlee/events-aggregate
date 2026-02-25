"""CivicRec (CivicPlus) event/activity scrapers.

CivicRec is a municipal recreation management system used by some Bay Area cities.
It is primarily a class/activity registration platform (swim lessons, camps, classes).

API status:
  The CivicRec platform documents public GET APIs, but in practice the tested endpoints
  at ca-paloalto.civicrec.com returned HTML rather than JSON without authentication.
  This scraper attempts the JSON API and falls back gracefully, logging a warning and
  returning [] — the same pattern as the CivicPlus city scrapers that return 403.

  Endpoints tried (in order):
    GET /api/v1/activities?format=json
    GET /api/v1/events?format=json
"""

from __future__ import annotations

import logging
from typing import Optional

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)


class CivicRecScraper(BaseScraper):
    """
    Generic scraper for CivicRec-hosted municipal recreation event catalogs.

    Args:
        source_name: Display name shown in the UI.
        base_url:    Root URL of the CivicRec instance (e.g. "https://ca-paloalto.civicrec.com").
    """

    def __init__(self, source_name: str, base_url: str):
        super().__init__(source_name, "city")
        self.base_url = base_url.rstrip("/")

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start_date, end_date = self.date_range(days_ahead)
        events: list[Event] = []

        api_endpoints = [
            f"{self.base_url}/api/v1/activities",
            f"{self.base_url}/api/v1/events",
        ]

        for endpoint in api_endpoints:
            try:
                params = {
                    "format": "json",
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                }
                resp = self.session.get(endpoint, params=params, timeout=15)
                content_type = resp.headers.get("Content-Type", "")
                if resp.status_code == 200 and "json" in content_type:
                    data = resp.json()
                    raw = data if isinstance(data, list) else data.get("activities") or data.get("events") or []
                    for item in raw:
                        ev = self._parse_activity(item)
                        if ev:
                            events.append(ev)
                    if events:
                        logger.info(f"[{self.source_name}] {len(events)} events via {endpoint}")
                        return events
                else:
                    logger.debug(
                        f"[{self.source_name}] {endpoint} returned "
                        f"HTTP {resp.status_code} / {content_type[:40]}"
                    )
            except Exception as exc:
                logger.debug(f"[{self.source_name}] {endpoint} failed: {exc}")

        logger.warning(
            f"[{self.source_name}] No accessible JSON API found. "
            "CivicRec may require authentication. Returning 0 events."
        )
        return []

    def _parse_activity(self, item: dict) -> Optional[Event]:
        try:
            title = (item.get("name") or item.get("title") or "").strip()
            if not title:
                return None

            date_str = (item.get("startDate") or item.get("start_date") or "")[:10]
            if not date_str:
                return None

            url = item.get("url") or item.get("link") or self.base_url
            location = item.get("location") or item.get("facility") or None
            description = (item.get("description") or "").strip()[:500] or None

            ev = Event(
                id=make_id(self.source_name, title, date_str),
                title=title,
                url=url,
                source=self.source_name,
                source_type="city",
                date_start=date_str,
                location=location,
                description=description,
            )
            ev = self.tag_kids(ev)
            return ev
        except Exception as exc:
            logger.debug(f"[{self.source_name}] parse_activity failed: {exc}")
            return None


# ---------------------------------------------------------------------------
# Concrete city instances
# ---------------------------------------------------------------------------

class PaloAltoCCScraper(CivicRecScraper):
    """Palo Alto Community Centers & Recreation (CivicRec)."""
    def __init__(self):
        super().__init__(
            source_name="Palo Alto Community Centers",
            base_url="https://ca-paloalto.civicrec.com",
        )
