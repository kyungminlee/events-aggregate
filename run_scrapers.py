#!/usr/bin/env python3
"""
Run all Bay Area event scrapers and write the results to site/data/events.json.

Usage:
    python run_scrapers.py              # fetch 60 days ahead (default)
    python run_scrapers.py --days 90   # fetch 90 days ahead
    python run_scrapers.py --kids-only # only include kids/family events
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_scrapers")

# ---------------------------------------------------------------------------
OUTPUT_PATH = Path(__file__).parent / "site" / "data" / "events.json"


def build_scrapers():
    """Return all configured scraper instances."""
    from scrapers.san_jose import SanJoseScraper
    from scrapers.mountain_view import MountainViewScraper
    from scrapers.sunnyvale import SunnyvaleScraper
    from scrapers.palo_alto import PaloAltoScraper
    from scrapers.menlo_park import MenloParkScraper
    from scrapers.civicplus import (
        CampbellScraper,
        GilroyScraper,
        MilpitasScraper,
        MorganHillScraper,
        SaratogaScraper,
    )
    from scrapers.eventbrite import DonEdwardsScraper, MidpenScraper
    from scrapers.hidden_villa import HiddenVillaScraper
    from scrapers.sccparks import SCCParksScraper
    from scrapers.libcal import MVPLScraper
    from scrapers.libraries import all_library_scrapers

    return [
        SanJoseScraper(),
        MountainViewScraper(),
        SunnyvaleScraper(),
        PaloAltoScraper(),
        MenloParkScraper(),
        MilpitasScraper(),
        CampbellScraper(),
        SaratogaScraper(),
        MorganHillScraper(),
        GilroyScraper(),
        DonEdwardsScraper(),
        MidpenScraper(),
        HiddenVillaScraper(),
        SCCParksScraper(),
        MVPLScraper(),
        *all_library_scrapers(),
    ]


def run(days_ahead: int = 60, kids_only: bool = False) -> int:
    scrapers = build_scrapers()
    all_events = []
    errors = []

    for scraper in scrapers:
        try:
            events = scraper.fetch_events(days_ahead=days_ahead)
            logger.info(f"  ✓ {scraper.source_name}: {len(events)} events")
            all_events.extend(events)
        except Exception as exc:
            logger.error(f"  ✗ {scraper.source_name}: {exc}")
            errors.append({"source": scraper.source_name, "error": str(exc)})

    if kids_only:
        all_events = [e for e in all_events if e.is_kids_event]
        logger.info(f"Filtered to {len(all_events)} kids/family events")

    # Sort by date ascending, then by title
    all_events.sort(key=lambda e: (e.date_start, e.time_start or "00:00", e.title))

    # Remove duplicates by id (keep first occurrence)
    seen: set[str] = set()
    deduped = []
    for ev in all_events:
        if ev.id not in seen:
            seen.add(ev.id)
            deduped.append(ev)

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(deduped),
        "kids_total": sum(1 for e in deduped if e.is_kids_event),
        "library_total": sum(1 for e in deduped if e.source_type == "library"),
        "sources": sorted({e.source for e in deduped}),
        "errors": errors,
        "events": [e.to_dict() for e in deduped],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info(
        f"\nDone! {len(deduped)} events saved to {OUTPUT_PATH}\n"
        f"  Kids/family: {output['kids_total']}\n"
        f"  Library:     {output['library_total']}\n"
        f"  Errors:      {len(errors)}"
    )
    return len(errors)


def main():
    parser = argparse.ArgumentParser(description="Scrape Bay Area city & library events")
    parser.add_argument("--days", type=int, default=60, help="Days ahead to fetch (default: 60)")
    parser.add_argument("--kids-only", action="store_true", help="Only save kids/family events")
    args = parser.parse_args()

    error_count = run(days_ahead=args.days, kids_only=args.kids_only)
    sys.exit(1 if error_count > 0 else 0)


if __name__ == "__main__":
    main()
