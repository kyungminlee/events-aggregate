"""Library event scrapers for the Bay Area region.

Sources:
  - Santa Clara County Library (SCCL) — BiblioCommons JSON API
    Covers branches: Sunnyvale, Campbell, Cupertino, Gilroy, Los Altos,
    Milpitas, Monte Sereno, Morgan Hill, Saratoga
  - San Jose Public Library (SJPL) — BiblioCommons JSON API
    (sjpl.org/events is a BiblioCommons site — same API pattern as SCCL)

BiblioCommons API (verified):
  GET https://{library}.bibliocommons.com/events
  Required headers: Accept: application/json, X-Requested-With: XMLHttpRequest
  Params:
    audience = KID | TEEN | FAMILY | ADULT
    page     = 1..N
    limit    = 24 (default)
  Response: {"events": [...], "count": N, "pages": N, "page": N, "limit": N}

  Each event:
    id, key, series_id,
    definition: { start, end, title, description, branch_location_id,
                  location_details, audience_ids, ... }
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional
from urllib.parse import urljoin

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BiblioCommons branch code → human-readable name
# ---------------------------------------------------------------------------

SCCL_BRANCH_NAMES: dict[str, str] = {
    "SU": "Sunnyvale",
    "CA": "Campbell",
    "CU": "Cupertino",
    "LA": "Los Altos",
    "MI": "Milpitas",
    "MS": "Monte Sereno",
    "MH": "Morgan Hill",
    "GI": "Gilroy",
    "SA": "Saratoga",
}

SJPL_BRANCH_NAMES: dict[str, str] = {
    # San José Public Library branch codes (approximate)
    "BER": "Berryessa", "CAM": "Cambrian", "EAS": "East San José",
    "EVI": "Evergreen", "HIM": "Hillview", "LIT": "Literacy",
    "MAG": "Magistrate", "MIL": "Milpitas", "NEW": "Nuevas Fronteras",
    "NOR": "Northwest", "POI": "Point", "ROC": "Rose Garden",
    "SMN": "San Martin", "SNO": "Snell", "SRR": "Santee",
    "TUL": "Tully", "VIN": "Vineland", "WES": "West Valley",
    "WHI": "Willow Glen", "ZAN": "Zanker",
}

_BC_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}
_BC_KIDS_AUDIENCES = ["KID", "TEEN", "FAMILY"]


# ---------------------------------------------------------------------------
# Generic BiblioCommons scraper
# ---------------------------------------------------------------------------

class BiblioCommonsScraper(BaseScraper):
    """
    Scraper for any BiblioCommons-hosted library event catalog.

    Args:
        source_name:   Display name ("Santa Clara County Library").
        bc_subdomain:  BiblioCommons subdomain, e.g. "sccl" or "sjpl".
        branch_map:    Dict mapping branch_location_id code → branch name.
    """

    def __init__(self, source_name: str, bc_subdomain: str,
                 branch_map: Optional[dict[str, str]] = None):
        super().__init__(source_name, "library")
        self.base_url = f"https://{bc_subdomain}.bibliocommons.com"
        self.branch_map = branch_map or {}
        self.session.headers.update(_BC_HEADERS)

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        events: list[Event] = []
        seen: set[str] = set()
        start, end = self.date_range(days_ahead)

        for audience in _BC_KIDS_AUDIENCES:
            for page in range(1, 50):
                params = {
                    "audience": audience,
                    "page": page,
                    "limit": 24,
                }
                try:
                    data = self.get_json(f"{self.base_url}/events", params=params)
                    raw = data.get("events", [])
                    if not raw:
                        break
                    for item in raw:
                        ev = self._parse_event(item, audience)
                        if ev and ev.id not in seen:
                            # Filter to requested date range
                            if ev.date_start >= start.isoformat() and ev.date_start <= end.isoformat():
                                seen.add(ev.id)
                                events.append(ev)
                    total_pages = data.get("pages", 1)
                    if page >= total_pages:
                        break
                    # Stop paging once we're past the end date
                    if raw and raw[-1].get("definition", {}).get("start", "") > end.isoformat():
                        break
                except Exception as exc:
                    logger.warning(f"[{self.source_name}] {audience} page {page} failed: {exc}")
                    break

        logger.info(f"[{self.source_name}] {len(events)} events fetched")
        return events

    def _parse_event(self, item: dict, audience: str) -> Optional[Event]:
        try:
            defn = item.get("definition") or {}
            title = (defn.get("title") or "").strip()
            if not title:
                return None

            start_raw = defn.get("start") or item.get("key", "")
            end_raw = defn.get("end")

            from dateutil import parser as dp
            dt_start = dp.parse(start_raw)
            date_str = dt_start.strftime("%Y-%m-%d")
            time_str = dt_start.strftime("%H:%M") if (dt_start.hour or dt_start.minute) else None

            date_end = time_end = None
            if end_raw:
                dt_end = dp.parse(end_raw)
                date_end = dt_end.strftime("%Y-%m-%d")
                time_end = dt_end.strftime("%H:%M") if (dt_end.hour or dt_end.minute) else None

            # URL
            event_id = item.get("id", "")
            event_key = (item.get("key") or "").replace(":", "-").replace("T", "-")
            url = f"{self.base_url}/events/{event_id}"

            # Location: branch + room
            branch_code = defn.get("branch_location_id") or ""
            branch_name = self.branch_map.get(branch_code, branch_code)
            room = defn.get("location_details") or ""
            location = f"{branch_name} — {room}" if room else branch_name or None

            # Description: strip HTML tags
            raw_desc = defn.get("description") or ""
            desc = re.sub(r"<[^>]+>", " ", raw_desc).strip()[:500]

            categories = [audience]

            ev = Event(
                id=make_id(self.source_name, title, date_str),
                title=title,
                url=url,
                source=self.source_name,
                source_type="library",
                date_start=date_str,
                date_end=date_end,
                time_start=time_str,
                time_end=time_end,
                location=location,
                description=desc,
                categories=categories,
            )
            # Audience hint from API + keyword check
            audience_is_kids = audience in ("KID", "TEEN", "FAMILY")
            ev.is_kids_event = audience_is_kids or self.tag_kids(ev).is_kids_event
            return ev
        except Exception as exc:
            logger.debug(f"[{self.source_name}] parse_event failed: {exc}")
            return None


# ---------------------------------------------------------------------------
# Concrete library instances
# ---------------------------------------------------------------------------

class SCCLScraper(BiblioCommonsScraper):
    """Santa Clara County Library (all branches)."""
    def __init__(self):
        super().__init__(
            source_name="Santa Clara County Library",
            bc_subdomain="sccl",
            branch_map=SCCL_BRANCH_NAMES,
        )


class SJPLScraper(BiblioCommonsScraper):
    """San José Public Library."""
    def __init__(self):
        super().__init__(
            source_name="San José Public Library",
            bc_subdomain="sjpl",
            branch_map=SJPL_BRANCH_NAMES,
        )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def all_library_scrapers() -> list[BaseScraper]:
    return [SJPLScraper(), SCCLScraper()]
