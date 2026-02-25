"""LibCal event scrapers (Springshare platform).

LibCal is used by many public libraries for event calendars.

iCal Feed (used instead of the AJAX JSON API):
  URL: https://{subdomain}.libcal.com/ical_subscribe.php?src=p&cid={cal_id}&aud={ids}
  Format: RFC 5545 iCalendar (VCALENDAR / VEVENT blocks)
  Params:
    src  = p (public)
    cid  = calendar ID (integer)
    aud  = comma-separated audience IDs to filter (e.g. "351,734,880,352,439")

  iCal VEVENT fields used:
    DTSTART, DTEND  — UTC timestamps ("YYYYMMDDTHHMMSSZ") or local ("YYYYMMDDTHHMMSS")
    SUMMARY         — event title
    DESCRIPTION     — plain text description (newlines escaped as \\n)
    LOCATION        — venue / room name
    CATEGORIES      — comma-separated category names
    UID             — stable unique ID ("LibCal-{cid}-{event_id}")
    URL             — canonical event page

  Audience IDs for Mountain View Public Library (kids/family):
    351  Babies
    734  Children
    880  Parents
    352  Preschoolers
    439  Tweens

Note: The AJAX JSON API (/ajax/calendar/list) uses 'date' as an *exact date*
filter, not a start-date — making it unsuitable for fetching a date range.
The iCal feed returns all upcoming events in a single request.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)

# Default kids/family audience IDs (Mountain View Public Library verified)
_DEFAULT_AUD = "351,734,880,352,439"


class LibCalScraper(BaseScraper):
    """
    Generic scraper for LibCal-hosted library event calendars.
    Fetches events via the iCal subscription feed.

    Args:
        source_name:  Display name shown in the UI.
        subdomain:    LibCal subdomain (e.g. "mountainview").
        cal_id:       LibCal calendar ID (integer).
        audience_ids: Comma-separated audience ID string for the iCal URL.
    """

    def __init__(self, source_name: str, subdomain: str, cal_id: int,
                 audience_ids: str = _DEFAULT_AUD):
        super().__init__(source_name, "library")
        self.base_url = f"https://{subdomain}.libcal.com"
        self.cal_id = cal_id
        self.ical_url = (
            f"{self.base_url}/ical_subscribe.php"
            f"?src=p&cid={cal_id}&aud={audience_ids}"
        )

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start_date, end_date = self.date_range(days_ahead)
        pacific = ZoneInfo("America/Los_Angeles")

        try:
            resp = self.get(self.ical_url)
            raw_items = self._parse_ical(resp.text)
        except Exception as exc:
            logger.warning(f"[{self.source_name}] iCal fetch failed: {exc}")
            return []

        events: list[Event] = []
        seen: set[str] = set()

        for item in raw_items:
            ev = self._parse_vevent(item, pacific)
            if ev is None:
                continue
            if ev.date_start < start_date.isoformat() or ev.date_start > end_date.isoformat():
                continue
            if ev.id not in seen:
                seen.add(ev.id)
                events.append(ev)

        logger.info(f"[{self.source_name}] {len(events)} events fetched")
        return events

    @staticmethod
    def _parse_ical(text: str) -> list[dict[str, str]]:
        """Parse iCal text into a list of VEVENT property dicts.

        Handles RFC 5545 line folding (CRLF + whitespace continuation)
        and common text escape sequences (\\n, \\,).
        """
        # Unfold folded lines
        text = re.sub(r'\r?\n[ \t]', '', text)
        vevents: list[dict[str, str]] = []
        current: Optional[dict[str, str]] = None

        for line in text.splitlines():
            if line == 'BEGIN:VEVENT':
                current = {}
            elif line == 'END:VEVENT':
                if current is not None:
                    vevents.append(current)
                    current = None
            elif current is not None and ':' in line:
                # Strip property parameters (e.g. DTSTART;TZID=...: → DTSTART)
                key_part, _, value = line.partition(':')
                key = key_part.split(';')[0].upper()
                # Unescape iCal text: \\n → newline, \\, → comma
                value = value.replace('\\n', '\n').replace('\\,', ',')
                current[key] = value

        return vevents

    @staticmethod
    def _parse_ical_dt(dtstr: str, pacific: ZoneInfo) -> datetime:
        """Parse an iCal datetime string into Pacific local time."""
        dtstr = dtstr.strip()
        if dtstr.endswith('Z'):
            dt = datetime.strptime(dtstr, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        elif 'T' in dtstr:
            dt = datetime.strptime(dtstr, '%Y%m%dT%H%M%S').replace(tzinfo=pacific)
        else:
            # All-day event: YYYYMMDD
            return datetime.strptime(dtstr, '%Y%m%d').replace(tzinfo=pacific)
        return dt.astimezone(pacific)

    def _parse_vevent(self, item: dict[str, str], pacific: ZoneInfo) -> Optional[Event]:
        try:
            title = (item.get('SUMMARY') or '').strip()
            if not title:
                return None

            dtstart = item.get('DTSTART') or ''
            if not dtstart:
                return None

            dt_start = self._parse_ical_dt(dtstart, pacific)
            date_str = dt_start.strftime('%Y-%m-%d')
            time_str = dt_start.strftime('%H:%M') if (dt_start.hour or dt_start.minute) else None

            date_end = time_end = None
            dtend = item.get('DTEND') or ''
            if dtend:
                dt_end = self._parse_ical_dt(dtend, pacific)
                date_end = dt_end.strftime('%Y-%m-%d')
                time_end = dt_end.strftime('%H:%M') if (dt_end.hour or dt_end.minute) else None

            url = (item.get('URL') or self.base_url).strip()
            location = (item.get('LOCATION') or '').strip() or None

            # Description is plain text (already unescaped); trim to 500 chars
            desc = (item.get('DESCRIPTION') or '').strip()[:500] or None

            # Categories: comma-separated in iCal
            categories = [
                c.strip()
                for c in (item.get('CATEGORIES') or '').split(',')
                if c.strip()
            ]

            ev = Event(
                id=make_id(self.source_name, title, date_str),
                title=title,
                url=url,
                source=self.source_name,
                source_type='library',
                date_start=date_str,
                date_end=date_end,
                time_start=time_str,
                time_end=time_end,
                location=location,
                description=desc,
                categories=categories,
                is_kids_event=True,  # pre-filtered by kids audience IDs in iCal URL
            )
            # Keyword check as a sanity pass (preserves is_kids_event=True)
            self.tag_kids(ev)
            ev.is_kids_event = True
            return ev

        except Exception as exc:
            logger.debug(f"[{self.source_name}] parse_vevent failed: {exc}")
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
