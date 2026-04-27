"""Geocode event locations to lat/lng using a venue cache + Nominatim fallback.

Strategy:
  1. Maintain a persistent JSON cache at site/data/venues.json keyed by a
     normalized venue key (substring match against event.location).
  2. Pre-seed the cache with known library-branch addresses — Nominatim
     resolves these once, then results are committed to the repo so future
     runs hit the cache.
  3. For each event, find a matching venue key in the cache and copy
     lat/lng onto the event.  Events with no match stay without coordinates
     (the map view just skips them).

We use OpenStreetMap Nominatim (no API key, 1 req/sec per TOS).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
EVENTS_PATH = ROOT / "site" / "data" / "events.json"
VENUES_PATH = ROOT / "site" / "data" / "venues.json"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "events-aggregate/1.0 (github.com/kyungminlee/events-aggregate)"

# Known venues seeded with mailing addresses.  The KEY is matched as a
# case-insensitive substring against event.location; longer keys win on tie.
# The VALUE is the full address passed to Nominatim for lat/lng resolution.
SEED_VENUES: dict[str, dict] = {
    # --- San Jose Public Library branches -------------------------------
    "Alum Rock":                {"address": "3090 Alum Rock Ave, San Jose, CA 95127",      "display": "SJPL — Alum Rock"},
    "Almaden":                  {"address": "6445 Camden Ave, San Jose, CA 95120",         "display": "SJPL — Almaden"},
    "Alviso":                   {"address": "5050 N 1st St, San Jose, CA 95002",           "display": "SJPL — Alviso"},
    "Bascom":                   {"address": "1000 S Bascom Ave, San Jose, CA 95128",       "display": "SJPL — Bascom"},
    "Berryessa":                {"address": "3355 Noble Ave, San Jose, CA 95132",          "display": "SJPL — Berryessa"},
    "Biblioteca Latinoamericana":{"address":"921 S 1st St, San Jose, CA 95110",            "display": "SJPL — Biblioteca Latinoamericana"},
    "Cambrian":                 {"address": "1780 Hillsdale Ave, San Jose, CA 95124",      "display": "SJPL — Cambrian"},
    "Calabazas":                {"address": "1230 S Blaney Ave, San Jose, CA 95129",       "display": "SJPL — Calabazas"},
    "East SJ Carnegie":         {"address": "1102 E Santa Clara St, San Jose, CA 95116",   "display": "SJPL — East SJ Carnegie"},
    "Edenvale":                 {"address": "101 Branham Ln E, San Jose, CA 95111",        "display": "SJPL — Edenvale"},
    "Educational Park":         {"address": "1772 Educational Park Dr, San Jose, CA 95133","display": "SJPL — Educational Park"},
    "Evergreen":                {"address": "2635 Aborn Rd, San Jose, CA 95121",           "display": "SJPL — Evergreen"},
    "Hillview":                 {"address": "1600 Hopkins Dr, San Jose, CA 95122",         "display": "SJPL — Hillview"},
    "Joyce Ellington":          {"address": "491 E Empire St, San Jose, CA 95112",         "display": "SJPL — Joyce Ellington"},
    "King Library":             {"address": "150 E San Fernando St, San Jose, CA 95112",   "display": "SJPL — Dr. Martin Luther King Jr."},
    "Mt. Pleasant":             {"address": "3090 S White Rd, San Jose, CA 95148",         "display": "SJPL — Mt. Pleasant"},
    "Pearl Avenue":             {"address": "4270 Pearl Ave, San Jose, CA 95136",          "display": "SJPL — Pearl Avenue"},
    "Rose Garden":              {"address": "1580 Naglee Ave, San Jose, CA 95126",         "display": "SJPL — Rose Garden"},
    "Santa Teresa":             {"address": "290 International Cir, San Jose, CA 95119",   "display": "SJPL — Santa Teresa"},
    "Seven Trees":              {"address": "3597 Cas Dr, San Jose, CA 95111",             "display": "SJPL — Seven Trees"},
    "Tully":                    {"address": "880 Tully Rd, San Jose, CA 95111",            "display": "SJPL — Tully"},
    "Vineland":                 {"address": "1450 Blossom Hill Rd, San Jose, CA 95118",    "display": "SJPL — Vineland"},
    "West Valley":              {"address": "1243 San Tomas Aquino Rd, San Jose, CA 95117","display": "SJPL — West Valley"},
    "Willow Glen":              {"address": "1157 Minnesota Ave, San Jose, CA 95125",      "display": "SJPL — Willow Glen"},

    # --- Santa Clara County Library branches ----------------------------
    "Cupertino":                {"address": "10800 Torre Ave, Cupertino, CA 95014",        "display": "SCCL — Cupertino"},
    "Campbell":                 {"address": "77 Harrison Ave, Campbell, CA 95008",         "display": "SCCL — Campbell"},
    "Gilroy":                   {"address": "350 W 6th St, Gilroy, CA 95020",              "display": "SCCL — Gilroy"},
    "Los Altos":                {"address": "13 S San Antonio Rd, Los Altos, CA 94022",    "display": "SCCL — Los Altos"},
    "Milpitas":                 {"address": "160 N Main St, Milpitas, CA 95035",           "display": "SCCL — Milpitas"},
    "Morgan Hill":              {"address": "660 W Main Ave, Morgan Hill, CA 95037",       "display": "SCCL — Morgan Hill"},
    "Saratoga":                 {"address": "13650 Saratoga Ave, Saratoga, CA 95070",      "display": "SCCL — Saratoga"},
    "Woodland":                 {"address": "1975 Grant Rd, Los Altos, CA 94024",          "display": "SCCL — Woodland"},

    # --- Palo Alto City Library branches --------------------------------
    "Rinconada Library":        {"address": "1213 Newell Rd, Palo Alto, CA 94303",         "display": "Palo Alto — Rinconada"},
    "Mitchell Park Library":    {"address": "3700 Middlefield Rd, Palo Alto, CA 94303",    "display": "Palo Alto — Mitchell Park"},
    "Downtown Library":         {"address": "270 Forest Ave, Palo Alto, CA 94301",         "display": "Palo Alto — Downtown"},
    "Children's Library":       {"address": "1276 Harriet St, Palo Alto, CA 94301",        "display": "Palo Alto — Children's Library"},
    "College Terrace":          {"address": "2300 Wellesley St, Palo Alto, CA 94306",      "display": "Palo Alto — College Terrace"},

    # --- Santa Clara City Library branches ------------------------------
    "Central Park Library":     {"address": "2635 Homestead Rd, Santa Clara, CA 95051",    "display": "SCCity — Central Park"},
    "Mission Branch Library":   {"address": "1098 Lexington St, Santa Clara, CA 95050",    "display": "SCCity — Mission"},
    "Northside Branch Library": {"address": "695 Moreland Way, Santa Clara, CA 95051",     "display": "SCCity — Northside"},

    # --- Other city libraries -------------------------------------------
    "Menlo Park Library":       {"address": "800 Alma St, Menlo Park, CA 94025",           "display": "Menlo Park Library"},
    "Belle Haven Library":      {"address": "100 Terminal Ave, Menlo Park, CA 94025",      "display": "Belle Haven Library"},
    "Sunnyvale Public Library": {"address": "665 W Olive Ave, Sunnyvale, CA 94086",        "display": "Sunnyvale Public Library"},
    "MV Library":               {"address": "585 Franklin St, Mountain View, CA 94041",    "display": "Mountain View Library"},

    # --- Parks & other recurring venues ---------------------------------
    "Hidden Villa":             {"address": "26870 Moody Rd, Los Altos Hills, CA 94022",   "display": "Hidden Villa"},
    "Martial Cottle Park":      {"address": "5283 Snell Ave, San Jose, CA 95136",          "display": "Martial Cottle Park"},
    "Joseph D. Grant County Park":{"address":"Joseph D. Grant County Park, Santa Clara County, CA",  "display": "Joseph D. Grant County Park"},
    "Magical Bridge Playground":{"address": "3700 Middlefield Rd, Palo Alto, CA 94306",    "display": "Magical Bridge Playground"},
    "Palo Alto Children's Theatre":{"address":"1305 Middlefield Rd, Palo Alto, CA 94301", "display": "Palo Alto Children's Theatre"},
    "Russian Ridge":            {"address": "Russian Ridge Open Space Preserve, San Mateo County, CA",          "display": "Russian Ridge Preserve"},
    "Windy Hill":               {"address": "555 Portola Rd, Portola Valley, CA 94028",    "display": "Windy Hill Preserve"},
    "Picchetti Ranch":          {"address": "13100 Montebello Rd, Cupertino, CA 95014",    "display": "Picchetti Ranch"},
    "San Francisco Bay National Wildlife Refuge":{"address":"2 Marshlands Rd, Fremont, CA 94555", "display": "Don Edwards SF Bay NWR"},
    "Pioneer Park":             {"address": "1100 Church St, Mountain View, CA 94041",     "display": "Pioneer Park (Mountain View)"},
    "Veterans Plaza":           {"address": "457 E Calaveras Blvd, Milpitas, CA 95035",    "display": "Veterans Plaza"},
    "Council Chamber":          {"address": "70 N First St, Campbell, CA 95008",           "display": "Campbell Council Chamber"},
    "Centennial Recreation":    {"address": "171 W Edmundson Ave, Morgan Hill, CA 95037",  "display": "Centennial Recreation Center"},
    "Villa Mira Monte":         {"address": "17860 Monterey Rd, Morgan Hill, CA 95037",    "display": "Villa Mira Monte"},
    "Masonic Center":           {"address": "380 W Dunne Ave, Morgan Hill, CA 95037",      "display": "Masonic Center (Morgan Hill)"},
    "Oak Room at the Arrillaga":{"address":"700 Alma St, Menlo Park, CA 94025",           "display": "Arrillaga Family Recreation Center"},
    "Columbia Neighborhood Center":{"address":"785 Morse Ave, Sunnyvale, CA 94085",       "display": "Columbia Neighborhood Center"},
    "Mountain View Senior Center":{"address":"266 Escuela Ave, Mountain View, CA 94040",  "display": "Mountain View Senior Center"},
    "Village Square":           {"address": "1100 Church St, Mountain View, CA 94041",     "display": "Village Square Community Room"},
    "City Hall":                {"address": "456 W Olive Ave, Sunnyvale, CA 94086",        "display": "Sunnyvale City Hall"},
    "Casa Grande":              {"address": "21350 Almaden Rd, San Jose, CA 95120",        "display": "Casa Grande — Almaden Quicksilver"},
    "Sanborn":                  {"address": "16055 Sanborn Rd, Saratoga, CA 95070",        "display": "Sanborn County Park"},
    "San Ysidro Park":          {"address": "7700 Murray Ave, Gilroy, CA 95020",           "display": "San Ysidro Park"},
    "Regional Water Quality Control Plant":{"address":"2501 Embarcadero Way, Palo Alto, CA 94303", "display": "Regional Water Quality Control Plant"},
    "Household Hazardous Waste Station":{"address":"2501 Embarcadero Way, Palo Alto, CA 94303", "display": "Household Hazardous Waste Station"},
}


def _nominatim(address: str) -> Optional[tuple[float, float]]:
    """Call Nominatim; return (lat, lng) or None on failure."""
    params = {"q": address, "format": "json", "limit": 1, "countrycodes": "us"}
    url = f"{NOMINATIM_URL}?{urlencode(params)}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as exc:
        logger.warning(f"Nominatim failed for {address!r}: {exc}")
        return None


def _load_cache() -> dict:
    if VENUES_PATH.exists():
        with VENUES_PATH.open() as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    VENUES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with VENUES_PATH.open("w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)


def _match_venue(location: str, cache: dict) -> Optional[str]:
    """Find the longest venue key that's a substring of location (case-insensitive)."""
    if not location:
        return None
    lower = location.lower()
    best_key, best_len = None, 0
    for key in cache:
        if key.lower() in lower and len(key) > best_len:
            best_key, best_len = key, len(key)
    return best_key


def update_cache(cache: dict, *, throttle: float = 1.1) -> dict:
    """Fill in lat/lng for any seed venues missing from the cache."""
    for key, info in SEED_VENUES.items():
        if key in cache and "lat" in cache[key]:
            # Already resolved — preserve any manual overrides.
            if "display" not in cache[key]:
                cache[key]["display"] = info["display"]
            if "address" not in cache[key]:
                cache[key]["address"] = info["address"]
            continue
        logger.info(f"Geocoding venue: {key} ({info['address']})")
        coords = _nominatim(info["address"])
        if coords is None:
            logger.warning(f"  skipped — no result for {key}")
            continue
        cache[key] = {
            "lat": coords[0],
            "lng": coords[1],
            "address": info["address"],
            "display": info["display"],
        }
        time.sleep(throttle)
    return cache


def annotate_events(events_path: Path = EVENTS_PATH, venues_path: Path = VENUES_PATH) -> int:
    """Load events.json, look up each event's venue, write lat/lng/venue_name back.

    Returns the number of events with coordinates.
    """
    cache = _load_cache()
    cache = update_cache(cache)
    _save_cache(cache)

    with events_path.open() as f:
        data = json.load(f)

    matched = 0
    for ev in data["events"]:
        loc = (ev.get("location") or "").strip()
        key = _match_venue(loc, cache)
        if key is None:
            ev["lat"] = None
            ev["lng"] = None
            ev["venue_name"] = None
            continue
        venue = cache[key]
        ev["lat"] = venue["lat"]
        ev["lng"] = venue["lng"]
        ev["venue_name"] = venue.get("display", key)
        matched += 1

    data["geocoded_total"] = matched
    with events_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Geocoded {matched} / {len(data['events'])} events ({100*matched//max(len(data['events']),1)}%)")
    return matched


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    annotate_events()
