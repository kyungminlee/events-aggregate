# Bay Area Kids & Family Events Aggregator

A static site that aggregates kids and family events from Bay Area city websites and public libraries, automatically updated daily via GitHub Actions and deployed to GitHub Pages.

## Live Site

Deployed to GitHub Pages — enable it under **Settings → Pages → Source: GitHub Actions**.

The site has two views:
- **Agenda** (`index.html`) — chronological list with search, date-range, and multi-source filters
- **Calendar** (`calendar.html`) — month or 2-week calendar grid; click a day to see its events

## Sources

### City Websites
| Source | URL | Platform | Status |
|--------|-----|----------|--------|
| City of Palo Alto | paloalto.gov | Granicus OpenCities | ✅ Working (curl_cffi Akamai bypass) |
| City of Menlo Park | menlopark.gov | Granicus OpenCities | ✅ Working |
| San Jose | sanjoseca.gov | Vision CMS (VisionLive) | ✅ Working (curl_cffi Akamai bypass) |
| Mountain View (city) | mountainview.gov | Vision CMS (VisionLive) | ✅ Working (curl_cffi Akamai bypass) |
| City of Sunnyvale | sunnyvale.ca.gov | Vision CMS (VisionLive) | ✅ Working (curl_cffi Akamai bypass) |
| City of Milpitas | milpitas.gov | CivicPlus CivicEngage (iCal) | ✅ Working |
| City of Campbell | campbellca.gov | CivicPlus CivicEngage (iCal) | ✅ Working |
| City of Saratoga | saratoga.ca.us | CivicPlus CivicEngage (iCal) | ✅ Working |
| City of Morgan Hill | morganhill.ca.gov | CivicPlus CivicEngage (iCal) | ✅ Working |
| City of Gilroy | cityofgilroy.org | CivicPlus CivicEngage (iCal) | ✅ Working |

Both OpenCities scrapers expand **recurring events**: the listing page shows only the first date, so each scraper follows the detail page to collect all individual occurrences.

CivicPlus cities share a single scraper (`scrapers/civicplus.py`) that pulls the `iCalendar.aspx?feed=calendar&catID=N` feed per category. Each city's concrete class selects the CIDs that actually publish kids/community events (some cities' "Main Calendar" CID is empty or is only meeting agendas).

### Venues, Parks & Nature Centers
| Source | URL | Platform | Status |
|--------|-----|----------|--------|
| Don Edwards SF Bay NWR | eventbrite.com/o/… | Eventbrite organizer page | ✅ Working |
| Midpen Open Space | eventbrite.com/o/… | Eventbrite organizer page | ⚠️ First page only (~12 of 30 events) |
| Santa Clara County Parks | parks.santaclaracounty.gov/events | Drupal (HTML scrape) | ✅ Working |

Eventbrite organizers share a single scraper (`scrapers/eventbrite.py`) that reads the Next.js `__NEXT_DATA__` blob embedded in the organizer page. Pagination beyond the first ~12 events requires the internal `/_next/data/...` endpoint (build-ID dependent) or an API token — not implemented yet.

The Santa Clara County Parks scraper (`scrapers/sccparks.py`) walks the Drupal views block in document order, associating `<h2>` date headers with the `.event-card` entries that follow. Covers naturalist programs across Martial Cottle, Coyote Creek, Sanborn, Almaden Quicksilver, Grant Ranch, and other county parks.

### Libraries
| Library | Platform | Status |
|---------|----------|--------|
| Mountain View Public Library | LibCal (Springshare) | ✅ Working |
| Palo Alto City Library (PACL) | BiblioCommons | ✅ Working |
| Santa Clara County Library (SCCL) | BiblioCommons | ✅ Working |
| San José Public Library (SJPL) | BiblioCommons RSS | ✅ Working (kids/family only) |

SCCL covers branches: Sunnyvale, Campbell, Cupertino, Gilroy, Los Altos, Milpitas, Monte Sereno, Morgan Hill, Saratoga.

## Local Development

```bash
# Create and activate a virtual environment (first time only)
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Run scrapers (fetches live data → site/data/events.json)
python run_scrapers.py

# Optional flags
python run_scrapers.py --days 90        # fetch 90 days ahead (default: 60)
python run_scrapers.py --kids-only      # only save kids/family events

# Serve the site locally
python -m http.server 8000 --directory site
# Open http://localhost:8000
```

If you use the `.claude/launch.json` dev server config, start the `site` configuration which runs the above server command using the `.venv` Python.

## Project Structure

```
├── scrapers/
│   ├── base.py           # Event dataclass + BaseScraper base class
│   ├── vision_cms.py     # Vision CMS / VisionLive (San Jose, Mountain View, Sunnyvale)
│   ├── opencities.py     # Granicus OpenCities generic scraper
│   ├── civicplus.py      # CivicPlus iCal scraper + Milpitas/Campbell/Saratoga/Morgan Hill/Gilroy
│   ├── eventbrite.py     # Eventbrite organizer-page scraper + Don Edwards, Midpen
│   ├── sccparks.py       # Santa Clara County Parks (Drupal HTML scrape)
│   ├── libcal.py         # Springshare LibCal (Mountain View Public Library)
│   ├── san_jose.py       # City-specific scraper instances
│   ├── mountain_view.py
│   ├── sunnyvale.py
│   ├── palo_alto.py
│   ├── menlo_park.py
│   └── libraries.py      # BiblioCommons scrapers: SCCL, SJPL, PACL
├── run_scrapers.py        # Orchestrator → site/data/events.json
├── requirements.txt
├── site/
│   ├── index.html         # Agenda view
│   ├── calendar.html      # Calendar view (month or 2-week grid)
│   ├── app.js             # Agenda view logic
│   ├── calendar.js        # Calendar view logic
│   ├── style.css
│   └── data/
│       └── events.json    # Generated by scrapers; committed as seed data
└── .github/
    └── workflows/
        └── scrape.yml     # Daily scrape + GitHub Pages deploy
```

## Data Model

Each event in `events.json` has:

```json
{
  "id": "abc123def456",
  "title": "Baby Storytime",
  "url": "https://...",
  "source": "Mountain View Public Library",
  "source_type": "library",
  "date_start": "2026-02-25",
  "date_end": null,
  "time_start": "10:30",
  "time_end": "11:15",
  "location": "1st Floor Program Room",
  "description": "...",
  "categories": ["Babies", "Children", "Families", "Storytime"],
  "is_kids_event": true,
  "is_free": null,
  "image_url": "https://..."
}
```

## Kids/Family Detection

Events are tagged `is_kids_event: true` if their title, description, or categories contain any of these keywords:

> kid, kids, child, children, youth, family, families, teen, teens, toddler, baby, infant, preschool, storytime, story time, puppet, craft, summer reading, after school, elementary, homework help, lego, young adult, jr., kindergarten, playdate

For BiblioCommons sources, the API `audience` field (`KID`, `TEEN`, `FAMILY`) is also used as a signal.

## Deployment

GitHub Actions runs daily at 8 AM PT (cron `0 15 * * *`) and on `workflow_dispatch`. It:
1. Runs `python run_scrapers.py` to fetch fresh events
2. Uploads `site/` as a GitHub Pages artifact
3. Deploys to GitHub Pages

Enable Pages under **Settings → Pages → Source: GitHub Actions** on the repo.
