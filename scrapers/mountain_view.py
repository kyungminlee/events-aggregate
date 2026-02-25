"""Scraper for City of Mountain View events.

Source: https://www.mountainview.gov/whats-happening/events
Platform: CivicPlus (CivicEngage)
"""

from .civicplus import CivicPlusScraper


class MountainViewScraper(CivicPlusScraper):
    def __init__(self):
        super().__init__(
            source_name="Mountain View",
            base_url="https://www.mountainview.gov",
            calendar_path="/whats-happening/events",
        )
