"""CivicPlus CivicEngage city-calendar scraper (iCal feed).

Used by many small/mid Bay Area cities (Milpitas, Campbell, Saratoga, Gilroy,
Morgan Hill, and more). All of them expose a common iCalendar endpoint:

  {base_url}/common/modules/iCalendar/iCalendar.aspx?feed=calendar&catID={cid}

Each category on the site has a numeric CID; the iCal feed only returns events
when a specific catID is requested (the "main" calendar without catID returns
an empty feed). Pick the CID(s) that correspond to Parks & Rec / community
events. Multiple CIDs can be merged for a single city.

The VEVENT blocks are already expanded (no RRULE on events — RRULE only
appears inside VTIMEZONE), so no recurrence expansion is needed here.

CivicPlus quirks:
- The DESCRIPTION field contains only the event URL (" https://.../calendar.aspx?EID=N")
  not a real description.
- The URL field points back to the feed and is useless. We build the event URL
  from UID (the numeric event ID): {base_url}/calendar.aspx?EID={UID}.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)


def _parse_ical(text: str) -> list[dict[str, str]]:
    """Parse iCal text into a list of VEVENT property dicts.

    Handles RFC 5545 line folding (CRLF + whitespace continuation)
    and common text escape sequences.
    """
    text = re.sub(r"\r?\n[ \t]", "", text)
    vevents: list[dict[str, str]] = []
    current: Optional[dict[str, str]] = None
    in_event = False
    for line in text.splitlines():
        if line == "BEGIN:VEVENT":
            current = {}
            in_event = True
        elif line == "END:VEVENT":
            if in_event and current is not None:
                vevents.append(current)
            current = None
            in_event = False
        elif in_event and current is not None and ":" in line:
            key_part, _, value = line.partition(":")
            key = key_part.split(";")[0].upper()
            value = value.replace("\\n", "\n").replace("\\,", ",")
            current[key] = value
    return vevents


def _parse_ical_dt(dtstr: str, pacific: ZoneInfo) -> datetime:
    dtstr = dtstr.strip()
    if dtstr.endswith("Z"):
        return datetime.strptime(dtstr, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(pacific)
    if "T" in dtstr:
        return datetime.strptime(dtstr, "%Y%m%dT%H%M%S").replace(tzinfo=pacific)
    return datetime.strptime(dtstr, "%Y%m%d").replace(tzinfo=pacific)


class CivicPlusScraper(BaseScraper):
    """
    Args:
        source_name:   Human-readable city label (e.g. "City of Milpitas").
        base_url:      Site root, e.g. "https://www.milpitas.gov".
        category_ids:  Single int or list of ints — CivicPlus calendar CIDs to merge.
    """

    def __init__(
        self,
        source_name: str,
        base_url: str,
        category_ids: int | list[int],
    ):
        super().__init__(source_name, "city")
        self.base_url = base_url.rstrip("/")
        self.category_ids = (
            [category_ids] if isinstance(category_ids, int) else list(category_ids)
        )

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start, end = self.date_range(days_ahead)
        start_iso, end_iso = start.isoformat(), end.isoformat()
        pacific = ZoneInfo("America/Los_Angeles")
        seen: set[str] = set()
        events: list[Event] = []

        for cid in self.category_ids:
            url = (
                f"{self.base_url}/common/modules/iCalendar/iCalendar.aspx"
                f"?feed=calendar&catID={cid}"
            )
            try:
                resp = self.get(url)
                vevents = _parse_ical(resp.text)
            except Exception as exc:
                logger.warning(f"[{self.source_name}] catID={cid} fetch failed: {exc}")
                continue

            for item in vevents:
                ev = self._build_event(item, pacific)
                if ev is None:
                    continue
                if ev.date_start < start_iso or ev.date_start > end_iso:
                    continue
                if ev.id in seen:
                    continue
                seen.add(ev.id)
                events.append(ev)

        logger.info(f"[{self.source_name}] {len(events)} events fetched")
        return events

    def _build_event(self, item: dict[str, str], pacific: ZoneInfo) -> Optional[Event]:
        try:
            title = (item.get("SUMMARY") or "").strip()
            uid = (item.get("UID") or "").strip()
            dtstart = (item.get("DTSTART") or "").strip()
            if not title or not dtstart:
                return None

            dt_start = _parse_ical_dt(dtstart, pacific)
            date_str = dt_start.strftime("%Y-%m-%d")
            time_str = dt_start.strftime("%H:%M") if (dt_start.hour or dt_start.minute) else None

            date_end = time_end = None
            dtend = (item.get("DTEND") or "").strip()
            if dtend:
                dt_end = _parse_ical_dt(dtend, pacific)
                end_date = dt_end.strftime("%Y-%m-%d")
                end_time = dt_end.strftime("%H:%M") if (dt_end.hour or dt_end.minute) else None
                if end_date != date_str:
                    date_end = end_date
                # CivicPlus often sets end to 23:59 for all-day-ish events — keep it as-is.
                time_end = end_time

            # Build a canonical event URL from the numeric UID.
            url = f"{self.base_url}/calendar.aspx?EID={uid}" if uid else self.base_url

            location = (item.get("LOCATION") or "").strip() or None
            # Description is just the event URL in CivicPlus feeds — drop it.
            desc = None

            id_key = f"{date_str}T{time_str}" if time_str else date_str
            ev = Event(
                id=make_id(self.source_name, title, id_key),
                title=title,
                url=url,
                source=self.source_name,
                source_type="city",
                date_start=date_str,
                date_end=date_end,
                time_start=time_str,
                time_end=time_end,
                location=location,
                description=desc,
            )
            return self.tag_kids(ev)
        except Exception as exc:
            logger.debug(f"[{self.source_name}] _build_event failed: {exc}")
            return None


# ---------------------------------------------------------------------------
# Concrete CivicPlus city instances
# ---------------------------------------------------------------------------

class MilpitasScraper(CivicPlusScraper):
    def __init__(self):
        super().__init__(
            source_name="City of Milpitas",
            base_url="https://www.milpitas.gov",
            # 14 = City Calendar, 26 = Recreation & Community Services
            category_ids=[14, 26],
        )


class CampbellScraper(CivicPlusScraper):
    def __init__(self):
        super().__init__(
            source_name="City of Campbell",
            base_url="https://www.campbellca.gov",
            # 14 = Main Calendar (already includes Rec items), 29 = Recreation & Community Services
            category_ids=[14, 29],
        )


class SaratogaScraper(CivicPlusScraper):
    """Saratoga Community Events.

    Saratoga's catID=14 is "City Hall Closures" only, so we use catID=35
    (Community Events) which has the actual public events.
    """
    def __init__(self):
        super().__init__(
            source_name="City of Saratoga",
            base_url="https://www.saratoga.ca.us",
            category_ids=35,  # Community Events
        )


class MorganHillScraper(CivicPlusScraper):
    """Morgan Hill Community + Centennial Recreation Center.

    catID=14 (City Government) is mostly commission meetings — skipped.
    catID=40 covers community events (farmers markets, scouts, etc.) and
    catID=44 covers Centennial Rec Center programming.
    """
    def __init__(self):
        super().__init__(
            source_name="City of Morgan Hill",
            base_url="https://www.morganhill.ca.gov",
            category_ids=[40, 44],
        )


class GilroyScraper(CivicPlusScraper):
    """Gilroy — Community Events + Youth Commission.

    catID=14 (Main Calendar) and catID=51 (Recreation) return empty iCal
    feeds, so we pull the categories that actually publish events.
    """
    def __init__(self):
        super().__init__(
            source_name="City of Gilroy",
            base_url="https://www.cityofgilroy.org",
            category_ids=[66, 54],  # Community Events, Youth Commission
        )
