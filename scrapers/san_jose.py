"""Scraper for City of San Jose events.

Source: https://www.sanjoseca.gov/news-stories/city-calendar
Platform: CivicPlus (CivicEngage)
"""

from .civicplus import CivicPlusScraper


class SanJoseScraper(CivicPlusScraper):
    def __init__(self):
        super().__init__(
            source_name="San Jose",
            base_url="https://www.sanjoseca.gov",
            calendar_path="/news-stories/city-calendar",
            # Calendar IDs for family/youth categories (update if needed after inspection)
            calendar_ids=[],
        )
