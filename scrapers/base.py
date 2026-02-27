"""Base scraper class, Event model, and shared utilities."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Keywords that indicate a kids/family event
KIDS_KEYWORDS = [
    "kid", "kids", "child", "children", "childhood", "youth",
    "family", "families", "teen", "teens", "toddler", "toddlers",
    "baby", "babies", "infant", "preschool", "pre-school", "prek", "pre-k",
    "kindergarten", "grade school", "elementary", "middle school",
    "storytime", "story time", "storytelling",
    "puppet", "puppets", "craft", "crafts",
    "summer reading", "reading program", "after school", "homework help",
    "lego", "minecraft", "young adult", "jr.", " jr ", "junior",
    "playdate", "play date", "swim lesson", "swim class",
    "children's", "kids'", "youth program",
]


def make_id(source: str, title: str, date_start: str) -> str:
    raw = f"{source}|{title}|{date_start}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def check_kids_keywords(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in KIDS_KEYWORDS)


@dataclass
class Event:
    id: str
    title: str
    url: str
    source: str          # e.g. "San Jose", "SCCL — Sunnyvale Branch"
    source_type: str     # "city" | "library"
    date_start: str      # YYYY-MM-DD
    date_end: Optional[str] = None
    time_start: Optional[str] = None   # HH:MM (24h)
    time_end: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    categories: list = field(default_factory=list)
    is_kids_event: bool = False
    is_free: Optional[bool] = None
    image_url: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class BaseScraper:
    """Abstract base for all event scrapers."""

    def __init__(self, source_name: str, source_type: str):
        self.source_name = source_name
        self.source_type = source_type
        self.session = requests.Session()
        self.session.headers.update(_DEFAULT_HEADERS)

    # ------------------------------------------------------------------ #
    #  Subclasses override this                                            #
    # ------------------------------------------------------------------ #
    def fetch_events(self, days_ahead: int = 60) -> list[Event]:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #
    def get(self, url: str, **kwargs) -> requests.Response:
        resp = self.session.get(url, timeout=20, **kwargs)
        resp.raise_for_status()
        return resp

    def get_json(self, url: str, **kwargs) -> dict | list:
        resp = self.get(url, **kwargs)   # delegates to self.get() so subclass overrides apply
        return resp.json()

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    def tag_kids(self, event: Event) -> Event:
        text = f"{event.title} {event.description or ''} {' '.join(event.categories)}"
        event.is_kids_event = check_kids_keywords(text)
        return event

    def date_range(self, days_ahead: int) -> tuple[date, date]:
        start = date.today()
        end = start + timedelta(days=days_ahead)
        return start, end
