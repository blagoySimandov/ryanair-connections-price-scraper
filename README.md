# Ryanair Flight Price Scraper

Finds the cheapest multi-stop Ryanair flights between any two airports. Fetches connection options from the Ryanair timetable API, scrapes individual leg prices, and ranks by total cost.

## Setup

```bash
pip install playwright httpx
playwright install chromium
```

## Usage

```bash
python main.py ORK SOF
python main.py ORK SOF --from 2026-03-26 --to 2026-04-18
python main.py ORK SOF --top 10
python main.py ORK SOF --no-scrape          # just list connections, skip prices
python main.py ORK SOF --input flights.json  # use saved connection data
python main.py ORK SOF --no-headless         # visible browser for debugging
```

## Options

| Flag            | Default               | Description                                    |
| --------------- | --------------------- | ---------------------------------------------- |
| `--from`        | today                 | Start date (YYYY-MM-DD)                        |
| `--to`          | +3 weeks              | End date (YYYY-MM-DD)                          |
| `--top`         | 5                     | Number of cheapest results to show             |
| `--no-scrape`   | -                     | List connections without scraping prices       |
| `--input`       | -                     | Load connections from JSON file instead of API |
| `--output`      | cheapest_flights.json | Output file path                               |
| `--no-headless` | -                     | Show browser window (debug bot detection)      |
| `--layover-min` | 1                     | Minimum layover hours                          |
| `--layover-max` | 8                     | Maximum layover hours                          |

## How it works

1. Fetches all connection options from the Ryanair timetable API
2. Deduplicates unique route/date legs to minimize page visits
3. Scrapes each Ryanair booking page with Playwright for flight card prices
4. Matches prices back to the full journey combinations
5. Outputs the cheapest journeys to stdout and JSON

## Notes

- Ryanair's site is JS-rendered Angular — Playwright with Chromium is required
- Use `--no-headless` if you hit bot detection
- 2s delay between requests to avoid rate limiting
