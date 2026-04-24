"""Santa Clara City Library scraper.

SCCity Library (3 branches: Central Park, Mission, Northside) runs the same
Vision CMS calendar as the City of Sunnyvale / SJ / MV. Event titles are
already prefixed with the branch in caps (e.g. "CENTRAL: Family Storytime"),
so no per-branch pagination is needed — the /calendar/events/all-events
grid lists every branch.
"""

from __future__ import annotations

from .vision_cms import VisionCMSScraper


class SantaClaraCityLibraryScraper(VisionCMSScraper):
    def __init__(self):
        super().__init__(
            source_name="Santa Clara City Library",
            base_url="https://www.sclibrary.org",
            calendar_path="/calendar/events/all-events",
            source_type="library",
        )
