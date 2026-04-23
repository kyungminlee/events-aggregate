"""Scraper for City of Mountain View events.

Source: https://www.mountainview.gov/whats-happening/events
Platform: Vision CMS — see scrapers/vision_cms.py for shared logic.
"""

from .vision_cms import VisionCMSScraper


class MountainViewScraper(VisionCMSScraper):
    def __init__(self):
        super().__init__(
            source_name="Mountain View",
            base_url="https://www.mountainview.gov",
            calendar_path="/whats-happening/events",
        )
