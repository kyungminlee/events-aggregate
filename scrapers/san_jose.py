"""Scraper for City of San Jose events.

Source: https://www.sanjoseca.gov/news-stories/city-calendar
Platform: Vision CMS — see scrapers/vision_cms.py for shared logic.
"""

from .vision_cms import VisionCMSScraper


class SanJoseScraper(VisionCMSScraper):
    def __init__(self):
        super().__init__(
            source_name="San Jose",
            base_url="https://www.sanjoseca.gov",
            calendar_path="/news-stories/city-calendar",
        )
