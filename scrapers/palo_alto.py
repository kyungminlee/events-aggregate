"""Scraper for City of Palo Alto events.

Source: https://www.paloalto.gov/Events-Directory
Platform: Granicus OpenCities (server-side rendered, pagination supported)

The Events-Directory page supports filtering by category and date range
via query parameters. We use startDate/endDate and optionally a kids
category filter.
"""

from .opencities import OpenCitiesScraper


class PaloAltoScraper(OpenCitiesScraper):
    def __init__(self):
        super().__init__(
            source_name="Palo Alto",
            base_url="https://www.paloalto.gov",
            events_path="/Events-Directory",
            # Palo Alto OpenCities supports neighborhood + category filters.
            # Uncomment and set the correct value if a "children" category exists:
            # kids_filter={"category": "children"},
            kids_filter={},
            max_pages=15,
        )
