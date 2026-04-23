"""Library event scrapers for the Bay Area region.

Sources:
  - Santa Clara County Library (SCCL) — BiblioCommons JSON API
    Covers branches: Sunnyvale, Campbell, Cupertino, Gilroy, Los Altos,
    Milpitas, Monte Sereno, Morgan Hill, Saratoga
  - San Jose Public Library (SJPL) — BiblioCommons RSS feed
    https://gateway.bibliocommons.com/v2/libraries/sjpl/rss/events
    (RSS returns more events and richer data than the JSON API)
  - Palo Alto City Library (PACL) — BiblioCommons JSON API
    Branches: Downtown, Mitchell Park, Children's Library

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

BiblioCommons RSS (SJPL):
  GET https://gateway.bibliocommons.com/v2/libraries/sjpl/rss/events
  Namespace: xmlns:bc="http://bibliocommons.com/rss/1.0/modules/event/"
  Fields: bc:start_date (UTC ISO), bc:start_date_local (YYYY-MM-DD),
          bc:location/bc:name (branch), bc:location/bc:location_details (room),
          bc:is_cancelled, category (audience text), enclosure (image)
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

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

PACL_BRANCH_NAMES: dict[str, str] = {
    # Palo Alto City Library branch codes (from API responses)
    "D": "Downtown Library",
    "M": "Mitchell Park Library",
    "C": "Children's Library",
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


class SJPLScraper(BaseScraper):
    """San José Public Library — RSS feed.

    Uses the paginated BiblioCommons RSS feed. The RSS is chronological
    (oldest first), so we paginate until all events exceed the end date.
    SJPL has 37 branches and thousands of events; we filter to kids/family only.

    Category names in RSS use the form "Kids, ages 5-10", "Teens, ages 12-18",
    etc., so we use substring matching rather than exact set membership.
    """

    RSS_URL = "https://gateway.bibliocommons.com/v2/libraries/sjpl/rss/events"
    BC_NS = "http://bibliocommons.com/rss/1.0/modules/event/"
    # Exact SJPL audience category names (lowercased) that indicate kids/family
    _KIDS_AUDIENCE_CATS = frozenset({
        "kids, ages 5-10",
        "pre-teens, ages 10-12",
        "teens, ages 12-18",
        "young children, ages 0-5",
        "families",
    })

    def __init__(self):
        super().__init__("San José Public Library", "library")

    def _bc(self, element, tag: str) -> Optional[str]:
        """Return the text of a bc:-namespaced child element."""
        child = element.find(f"{{{self.BC_NS}}}{tag}")
        return child.text if child is not None else None

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start_date, end_date = self.date_range(days_ahead)
        events: list[Event] = []
        seen: set[str] = set()

        # The RSS feed is chronological (oldest first). Paginate until all
        # events on the page are past our end date. 200 pages covers ~90 days.
        for page in range(1, 200):
            try:
                resp = self.get(self.RSS_URL, params={"page": page})
                root = ET.fromstring(resp.content)
            except Exception as exc:
                logger.warning(f"[{self.source_name}] page {page} failed: {exc}")
                break

            items = root.findall(".//item")
            if not items:
                break

            page_events = [ev for item in items if (ev := self._parse_item(item)) is not None]
            if not page_events:
                break

            for ev in page_events:
                if not ev.is_kids_event:
                    continue  # SJPL is too large to include all events
                if ev.id not in seen and start_date.isoformat() <= ev.date_start <= end_date.isoformat():
                    seen.add(ev.id)
                    events.append(ev)

            # Stop once all events on this page are past the window
            if all(ev.date_start > end_date.isoformat() for ev in page_events):
                break

        logger.info(f"[{self.source_name}] {len(events)} events fetched")
        return events

    def _parse_item(self, item) -> Optional[Event]:
        try:
            title = (item.findtext("title") or "").strip()
            if not title:
                return None

            # Skip cancelled events
            if (self._bc(item, "is_cancelled") or "false").lower() == "true":
                return None

            url = (item.findtext("link") or "").strip()

            # Dates: use local date fields; fall back to parsing UTC timestamps.
            # bc:start_date_local can be "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM" — take first 10 chars.
            pacific = ZoneInfo("America/Los_Angeles")
            _sdl = self._bc(item, "start_date_local")
            _edl = self._bc(item, "end_date_local")
            date_start_local = _sdl[:10] if _sdl else None
            date_end_local = _edl[:10] if _edl else None
            time_start = time_end = None

            start_utc = self._bc(item, "start_date")
            if start_utc:
                dt = datetime.fromisoformat(start_utc).astimezone(pacific)
                if not date_start_local:
                    date_start_local = dt.strftime("%Y-%m-%d")
                if dt.hour or dt.minute:
                    time_start = dt.strftime("%H:%M")

            end_utc = self._bc(item, "end_date")
            if end_utc:
                dt = datetime.fromisoformat(end_utc).astimezone(pacific)
                if not date_end_local:
                    date_end_local = dt.strftime("%Y-%m-%d")
                # SJPL marks all-day / time-TBD events with end_date 23:59 and no start_date;
                # treat that as an end-of-day sentinel rather than a real end time.
                if (dt.hour or dt.minute) and (dt.hour, dt.minute) != (23, 59):
                    time_end = dt.strftime("%H:%M")

            if not date_start_local:
                return None

            # Location: branch name + optional room
            bc_loc = item.find(f"{{{self.BC_NS}}}location")
            location = None
            if bc_loc is not None:
                branch = (bc_loc.findtext(f"{{{self.BC_NS}}}name") or "").strip() or None
                room = (bc_loc.findtext(f"{{{self.BC_NS}}}location_details") or "").strip() or None
                location = f"{branch} — {room}" if (branch and room) else branch or room

            # Description (HTML CDATA → strip tags)
            raw_desc = (item.findtext("description") or "").strip()
            desc = re.sub(r"<[^>]+>", " ", raw_desc).strip()[:500] or None

            # Audience categories
            categories = [c.text.strip() for c in item.findall("category") if c.text]

            # Image
            enclosure = item.find("enclosure")
            image_url = enclosure.get("url") if enclosure is not None else None

            ev = Event(
                id=make_id(self.source_name, title, date_start_local),
                title=title,
                url=url,
                source=self.source_name,
                source_type="library",
                date_start=date_start_local,
                date_end=date_end_local,
                time_start=time_start,
                time_end=time_end,
                location=location,
                description=desc,
                categories=categories,
                image_url=image_url,
            )

            # Kids detection: match against exact SJPL audience category names.
            # Don't use tag_kids() fallback — "Family Learning Centers" (a topic
            # category) would trigger false positives via the "family" keyword.
            cats_lower = {c.lower() for c in categories}
            ev.is_kids_event = bool(cats_lower & self._KIDS_AUDIENCE_CATS)
            return ev

        except Exception as exc:
            logger.debug(f"[{self.source_name}] parse_item failed: {exc}")
            return None


class PACLScraper(BiblioCommonsScraper):
    """Palo Alto City Library (PACL)."""
    def __init__(self):
        super().__init__(
            source_name="Palo Alto City Library",
            bc_subdomain="paloalto",
            branch_map=PACL_BRANCH_NAMES,
        )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def all_library_scrapers() -> list[BaseScraper]:
    return [SJPLScraper(), SCCLScraper(), PACLScraper()]
