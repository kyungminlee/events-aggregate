"""Scraper for City of Sunnyvale events.

Source: https://www.sunnyvale.ca.gov/news-center-and-events-calendar/city-calendar
Platform: Vision CMS — see scrapers/vision_cms.py for shared logic.
"""

from .vision_cms import VisionCMSScraper


class SunnyvaleScraper(VisionCMSScraper):
    def __init__(self):
        super().__init__(
            source_name="City of Sunnyvale",
            base_url="https://www.sunnyvale.ca.gov",
            calendar_path="/news-center-and-events-calendar/city-calendar",
        )
