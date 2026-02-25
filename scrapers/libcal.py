"""LibCal event scrapers (Springshare platform).

LibCal is used by many public libraries for event calendars.

API:
  GET https://{subdomain}.libcal.com/ajax/calendar/list
  Params:
    c        = calendar ID (integer)
    date     = YYYY-MM-DD (start date; returns events from this date forward)
    audience = numeric audience ID (optional filter)
    page     = 1..N
    perpage  = results per page (default 24)
  Response: {"total_results": N, "perpage": N, "status": 200, "results": [...]}

  Each event (flat structure):
    id, title, url
    startdt, enddt  — "YYYY-MM-DD HH:MM:SS"
    start, end      — "HH:MM am/pm" (human-readable time)
    location        — string (may also be in locations[0].name)
    locations       — [{id, name, map, ...}]
    shortdesc       — plain-text truncated description
    description     — full HTML description
    audiences       — [{id, name, color}]
    categories_arr  — [{cat_id, name, color}]
    featured_image  — URL string or ""
    online_event    — boolean
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Optional

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kids-relevant audience IDs on LibCal (Mountain View Public Library verified)
# ---------------------------------------------------------------------------
_KIDS_AUDIENCE_IDS = [
    734,    # Children
    5695,   # Families
    193,    # Teens
    351,    # Babies
    352,    # Preschoolers
    880,    # Parents
    10658,  # Toddlers
    439,    # Tweens
]


class LibCalScraper(BaseScraper):
    """
    Generic scraper for LibCal-hosted library event calendars.

    Args:
        source_name: Display name shown in the UI.
        subdomain:   LibCal subdomain (e.g. "mountainview").
        cal_id:      LibCal calendar ID (integer).
    """

    def __init__(self, source_name: str, subdomain: str, cal_id: int):
        super().__init__(source_name, "library")
        self.base_url = f"https://{subdomain}.libcal.com"
        self.cal_id = cal_id
        self._api_url = f"{self.base_url}/ajax/calendar/list"

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start_date, end_date = self.date_range(days_ahead)
        events: list[Event] = []
        seen: set[int] = set()  # LibCal event IDs are integers

        for aud_id in _KIDS_AUDIENCE_IDS:
            page = 1
            while True:
                params = {
                    "c": self.cal_id,
                    "date": start_date.isoformat(),
                    "audience": aud_id,
                    "page": page,
                    "perpage": 24,
                }
                try:
                    data = self.get_json(self._api_url, params=params)
                    results = data.get("results") or []
                    if not results:
                        break
                    for item in results:
                        ev = self._parse_event(item)
                        if ev is None:
                            continue
                        # Skip events beyond the requested window
                        if ev.date_start > end_date.isoformat():
                            continue
                        raw_id = item.get("id")
                        if raw_id in seen:
                            continue
                        seen.add(raw_id)
                        events.append(ev)

                    total = data.get("total_results", 0)
                    per_page = data.get("perpage", 24) or 24
                    total_pages = math.ceil(total / per_page) if total else 1
                    if page >= total_pages:
                        break
                    page += 1
                except Exception as exc:
                    logger.warning(
                        f"[{self.source_name}] audience={aud_id} page={page} failed: {exc}"
                    )
                    break

        logger.info(f"[{self.source_name}] {len(events)} events fetched")
        return events

    def _parse_event(self, item: dict) -> Optional[Event]:
        try:
            title = (item.get("title") or "").strip()
            if not title:
                return None

            # Dates: "YYYY-MM-DD HH:MM:SS"
            startdt = item.get("startdt") or ""
            enddt = item.get("enddt") or ""
            dt_start = datetime.strptime(startdt, "%Y-%m-%d %H:%M:%S")
            date_str = dt_start.strftime("%Y-%m-%d")
            time_str = dt_start.strftime("%H:%M") if (dt_start.hour or dt_start.minute) else None

            date_end = time_end = None
            if enddt:
                dt_end = datetime.strptime(enddt, "%Y-%m-%d %H:%M:%S")
                date_end = dt_end.strftime("%Y-%m-%d")
                time_end = dt_end.strftime("%H:%M") if (dt_end.hour or dt_end.minute) else None

            url = item.get("url") or self.base_url

            # Location: prefer locations array, fall back to location string
            location = None
            locs = item.get("locations") or []
            if locs and locs[0].get("name"):
                location = locs[0]["name"]
            elif item.get("location"):
                location = item["location"]

            # Description: use shortdesc (plain text) to avoid HTML
            description = (item.get("shortdesc") or "").strip() or None

            # Image
            image_url = item.get("featured_image") or None
            if image_url == "":
                image_url = None

            # Categories from audience and category names
            categories = [a["name"] for a in (item.get("audiences") or []) if a.get("name")]
            cat_names = [c["name"] for c in (item.get("categories_arr") or []) if c.get("name")]
            categories.extend(cat_names)

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
                description=description,
                categories=categories,
                is_kids_event=True,  # already filtered by kids audience IDs
                image_url=image_url,
            )
            # Also run keyword check as a sanity pass (keeps is_kids_event=True)
            ev = self.tag_kids(ev)
            ev.is_kids_event = True
            return ev
        except Exception as exc:
            logger.debug(f"[{self.source_name}] parse_event failed: {exc}")
            return None


# ---------------------------------------------------------------------------
# Concrete library instances
# ---------------------------------------------------------------------------

class MVPLScraper(LibCalScraper):
    """Mountain View Public Library (LibCal calendar ID 8800)."""
    def __init__(self):
        super().__init__(
            source_name="Mountain View Public Library",
            subdomain="mountainview",
            cal_id=8800,
        )
