# Ryanair Flight Price Scraper

Find the cheapest multi-stop Ryanair flights between any two airports.

Now includes:
- CLI mode (`python main.py ...`)
- Minimal web UI (React + shadcn-style components)
- Docker deployment for the web app

## Setup (CLI)

```bash
pip install -r requirements.txt
playwright install chromium
```

## CLI Usage

```bash
python main.py ORK SOF
python main.py ORK SOF --from 2026-03-26 --to 2026-04-18
python main.py ORK SOF --top 10
python main.py ORK SOF --no-scrape
python main.py ORK SOF --input flights.json
python main.py ORK SOF --no-headless
```

## Web UI (local)

### 1) Backend

```bash
pip install -r requirements.txt
playwright install chromium
uvicorn api:app --host 0.0.0.0 --port 8000
```

### 2) Frontend dev server (optional for local development)

```bash
cd web
npm install
npm run dev
```

Vite proxies `/api/*` to `http://localhost:8000`.

## Docker

Build and run:

```bash
docker build -t ryanair-scraper .
docker run --rm -p 8000:8000 ryanair-scraper
```

Then open `http://localhost:8000`.

## Feature coverage in UI

The web form exposes all existing app features:
- Origin / destination
- Date range (`--from`, `--to`)
- Top results (`--top`)
- No scrape mode (`--no-scrape`)
- Input JSON upload (`--input`)
- Output filename + JSON download (`--output`)
- No headless mode (`--no-headless`)
- Layover min/max (`--layover-min`, `--layover-max`)

## How it works

1. Fetches connection options from the Ryanair timetable API
2. Deduplicates route/date legs
3. Scrapes leg prices from ryanair.com with Playwright
4. Matches prices to journey combinations
5. Ranks and returns cheapest journeys
