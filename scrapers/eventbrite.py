"""Eventbrite organizer-page scraper.

Many Bay Area nature centers, museums, and small venues publish their
programming on Eventbrite instead of a standalone calendar. Each organizer has
a profile page at:

  https://www.eventbrite.com/o/{slug}-{organizer_id}

The page is a Next.js app — its server-rendered HTML embeds the full page
props in a <script id="__NEXT_DATA__"> blob. `props.pageProps.upcomingEvents`
is a ready-to-use array with name, url, start_date, start_time, timezone,
venue (incl. address), image, and ticket_availability.is_free.

Limitation: the org page only returns the first ~12 upcoming events
(`upcomingEventsTotal` is the true count; `hasMoreUpcoming` indicates more
exist). Fetching additional pages requires either an authenticated API token
or the internal Next.js /_next/data/{buildId}/... endpoint with a live build
ID, both of which are fragile to rely on. For now we take what the org page
gives us — that's the next ~2-4 weeks of programming for most venues.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Optional

from .base import BaseScraper, Event, make_id

logger = logging.getLogger(__name__)


class EventbriteScraper(BaseScraper):
    """
    Args:
        source_name:     Display label (e.g. "Don Edwards SF Bay NWR").
        organizer_slug:  Full slug-id string after /o/ in the Eventbrite URL,
                         e.g. "don-edwards-sf-bay-national-wildlife-refuge-6363846263".
    """

    def __init__(self, source_name: str, organizer_slug: str):
        super().__init__(source_name, "venue")
        self.organizer_slug = organizer_slug
        self.org_url = f"https://www.eventbrite.com/o/{organizer_slug}"

    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        start, end = self.date_range(days_ahead)
        start_iso, end_iso = start.isoformat(), end.isoformat()

        try:
            resp = self.get(self.org_url)
            raw_events, total, has_more = self._extract_events(resp.text)
        except Exception as exc:
            logger.warning(f"[{self.source_name}] fetch failed: {exc}")
            return []

        if has_more:
            logger.info(
                f"[{self.source_name}] organizer has {total} upcoming events "
                f"but Eventbrite page only returns {len(raw_events)} — "
                "paginated events will be missed"
            )

        events: list[Event] = []
        seen: set[str] = set()
        for raw in raw_events:
            ev = self._build_event(raw)
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

    @staticmethod
    def _extract_events(html: str) -> tuple[list[dict], int, bool]:
        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not m:
            return [], 0, False
        data = json.loads(m.group(1))
        pp = data.get("props", {}).get("pageProps", {})
        return (
            pp.get("upcomingEvents") or [],
            pp.get("upcomingEventsTotal") or 0,
            bool(pp.get("hasMoreUpcoming")),
        )

    def _build_event(self, raw: dict) -> Optional[Event]:
        try:
            title = (raw.get("name") or "").strip()
            date_start = raw.get("start_date")
            if not title or not date_start:
                return None
            if raw.get("is_cancelled"):
                return None

            # Eventbrite stores start_time / end_time as "HH:MM:SS" local to timezone.
            # If end_time == start_time it's a placeholder (no real end); drop it.
            time_start = _hhmm(raw.get("start_time"))
            time_end = _hhmm(raw.get("end_time"))
            if time_end and time_end == time_start:
                time_end = None

            date_end = raw.get("end_date")
            if date_end == date_start:
                date_end = None

            url = (raw.get("url") or self.org_url).strip()
            summary = (raw.get("summary") or "").strip() or None

            venue = raw.get("primary_venue") or {}
            location = None
            if venue:
                address = (venue.get("address") or {})
                location_parts = [
                    venue.get("name"),
                    address.get("localized_address_display"),
                ]
                location = " — ".join(p for p in location_parts if p) or None

            image = raw.get("image") or {}
            image_url = image.get("url") if isinstance(image, dict) else None

            is_free = None
            ticket = raw.get("ticket_availability") or {}
            if "is_free" in ticket:
                is_free = bool(ticket.get("is_free"))

            id_key = f"{date_start}T{time_start}" if time_start else date_start
            ev = Event(
                id=make_id(self.source_name, title, id_key),
                title=title,
                url=url,
                source=self.source_name,
                source_type=self.source_type,
                date_start=date_start,
                date_end=date_end,
                time_start=time_start,
                time_end=time_end,
                location=location,
                description=summary,
                is_free=is_free,
                image_url=image_url,
            )
            return self.tag_kids(ev)
        except Exception as exc:
            logger.debug(f"[{self.source_name}] _build_event failed: {exc}")
            return None


def _hhmm(time_str: Optional[str]) -> Optional[str]:
    """Convert 'HH:MM:SS' to 'HH:MM'; return None for empty/invalid input."""
    if not time_str:
        return None
    try:
        return datetime.strptime(time_str, "%H:%M:%S").strftime("%H:%M")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Concrete Eventbrite organizer instances
# ---------------------------------------------------------------------------

class DonEdwardsScraper(EventbriteScraper):
    """Don Edwards SF Bay National Wildlife Refuge — naturalist programs."""
    def __init__(self):
        super().__init__(
            source_name="Don Edwards SF Bay NWR",
            organizer_slug="don-edwards-sf-bay-national-wildlife-refuge-6363846263",
        )


class MidpenScraper(EventbriteScraper):
    """Midpeninsula Regional Open Space District — docent-led hikes and activities."""
    def __init__(self):
        super().__init__(
            source_name="Midpen Open Space",
            organizer_slug="midpeninsula-regional-open-space-district-12769299752",
        )
