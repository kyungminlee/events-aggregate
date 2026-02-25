"""Scraper for City of Sunnyvale events.

Source: https://www.sunnyvale.ca.gov/news-center-and-events-calendar/city-calendar
Platform: Granicus govAccess (CivicPlus calendar component embedded)
"""

from .civicplus import CivicPlusScraper


class SunnyvaleScraper(CivicPlusScraper):
    def __init__(self):
        super().__init__(
            source_name="Sunnyvale",
            base_url="https://www.sunnyvale.ca.gov",
            calendar_path="/news-center-and-events-calendar/city-calendar",
        )
