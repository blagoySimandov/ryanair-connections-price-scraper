"""
Ryanair Flight Price Scraper

Fetches multi-stop connection options from the Ryanair timetable API,
scrapes individual leg prices from ryanair.com, and outputs the cheapest
total journey options.
"""

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

TIMETABLE_API = "https://services-api.ryanair.com/timtbl/v3/journeys"
TIMETABLE_KEY = "c75263dd5ffbda4698843257b2e68fbb"
TIMETABLE_HEADERS = {
    "sec-ch-ua-platform": '"macOS"',
    "Referer": "https://ryanairconnections.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
}


@dataclass
class LegPrice:
    origin: str
    destination: str
    date: str
    departure_time: str
    arrival_time: str
    price: float | None
    url: str


@dataclass
class JourneyPrice:
    legs: list[LegPrice]
    total_price: float
    total_duration: str
    departure_datetime: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Ryanair for cheapest multi-stop flight prices.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("origin", help="Origin IATA code (e.g. ORK)")
    parser.add_argument("destination", help="Destination IATA code (e.g. SOF)")
    parser.add_argument("--from", dest="date_from", default=None, help="Start date YYYY-MM-DD (default: today)")
    parser.add_argument("--to", dest="date_to", default=None, help="End date YYYY-MM-DD (default: 3 weeks from start)")
    parser.add_argument("--top", type=int, default=5, help="Number of cheapest results to show (default: 5)")
    parser.add_argument("--no-scrape", action="store_true", help="Skip price scraping, just show available connections")
    parser.add_argument("--input", dest="input_file", default=None, help="Load connections from a JSON file instead of fetching from API")
    parser.add_argument("--output", dest="output_file", default="cheapest_flights.json", help="Output JSON file (default: cheapest_flights.json)")
    parser.add_argument("--no-headless", action="store_true", help="Run browser with visible window (for debugging bot detection)")
    parser.add_argument("--layover-min", type=int, default=1, help="Minimum layover hours (default: 1)")
    parser.add_argument("--layover-max", type=int, default=8, help="Maximum layover hours (default: 8)")

    args = parser.parse_args()
    args.date_from, args.date_to = resolve_dates(args.date_from, args.date_to)
    return args


def resolve_dates(date_from: str | None, date_to: str | None) -> tuple[str, str]:
    if date_from is None:
        date_from = datetime.now().strftime("%Y-%m-%d")
    if date_to is None:
        start = datetime.strptime(date_from, "%Y-%m-%d")
        date_to = (start + timedelta(weeks=3)).strftime("%Y-%m-%d")
    return date_from, date_to


def fetch_connections(
    origin: str,
    dest: str,
    date_from: str,
    date_to: str,
    layover_min: int = 1,
    layover_max: int = 8,
) -> list[dict]:
    url = (
        f"{TIMETABLE_API}/{origin}/{dest}"
        f"?departureDateFrom={date_from}"
        f"&departureDateTo={date_to}"
        f"&key={TIMETABLE_KEY}"
        f"&timeMode=LOCAL"
        f"&layoverFrom={layover_min}"
        f"&layoverTo={layover_max}"
    )

    print(f"Fetching connections {origin} -> {dest} ({date_from} to {date_to})...")
    resp = httpx.get(url, headers=TIMETABLE_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    print(f"Found {len(data)} connection options\n")
    return data


def build_ryanair_url(origin: str, dest: str, date: str) -> str:
    return (
        f"https://www.ryanair.com/ie/en/trip/flights/select?"
        f"adults=1&teens=0&children=0&infants=0"
        f"&dateOut={date}&dateIn="
        f"&isConnectedFlight=false&isReturn=false"
        f"&discount=0&promoCode="
        f"&originIata={origin}&destinationIata={dest}"
        f"&tpAdults=1&tpTeens=0&tpChildren=0&tpInfants=0"
        f"&tpStartDate={date}&tpEndDate="
        f"&tpDiscount=0&tpPromoCode="
        f"&tpDepartureIata={origin}&tpDestinationIata={dest}"
    )


def get_unique_legs(data: list[dict]) -> list[tuple[str, str, str]]:
    legs = set()
    for journey in data:
        for flight in journey["flights"]:
            dt = datetime.fromisoformat(flight["departureDateTime"])
            date_str = dt.strftime("%Y-%m-%d")
            legs.add((flight["departureAirportCode"], flight["arrivalAirportCode"], date_str))
    return sorted(legs)


async def scrape_prices_for_route(page, origin: str, dest: str, date: str) -> dict[str, float]:
    url = build_ryanair_url(origin, dest, date)
    print(f"  Scraping {origin} -> {dest} on {date}...")

    time_price_map: dict[str, float] = {}

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        try:
            await page.wait_for_selector("flight-card-new", timeout=15000)
        except Exception:
            print("    No flight cards found")
            return time_price_map

        try:
            cookie_btn = page.locator("button.cookie-popup-with-overlay__button, [data-ref='cookie.accept-all']")
            if await cookie_btn.count() > 0:
                await cookie_btn.first.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        await asyncio.sleep(2)

        cards = page.locator("flight-card-new")
        count = await cards.count()
        print(f"    Found {count} flights")

        for i in range(count):
            card = cards.nth(i)
            try:
                dep_time_el = card.locator("[data-ref='flight-segment.departure'] .flight-info__hour")
                dep_time = (await dep_time_el.inner_text()).strip()

                price_el = card.locator("[data-e2e='flight-card-price']")
                price_text = (await price_el.inner_text()).strip()

                price_clean = re.sub(r"[^\d.]", "", price_text)
                if price_clean:
                    price = float(price_clean)
                    time_price_map[dep_time] = price
                    print(f"    {dep_time} => £{price:.2f}")
            except Exception as e:
                print(f"    Error on card {i}: {e}")

    except Exception as e:
        print(f"    Page error: {e}")

    return time_price_map


async def scrape_all_prices(unique_legs: list[tuple[str, str, str]], headless: bool) -> dict[tuple[str, str, str], dict[str, float]]:
    from playwright.async_api import async_playwright

    cache: dict[tuple[str, str, str], dict[str, float]] = {}
    print(f"Scraping prices for {len(unique_legs)} unique route/date combos...\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        for origin, dest, date in unique_legs:
            cache[(origin, dest, date)] = await scrape_prices_for_route(page, origin, dest, date)
            await asyncio.sleep(2)

        await browser.close()

    return cache


def match_prices(connections: list[dict], price_cache: dict[tuple[str, str, str], dict[str, float]]) -> list[JourneyPrice]:
    results = []

    for journey in connections:
        legs = []
        total = 0.0
        all_found = True

        for flight in journey["flights"]:
            dt = datetime.fromisoformat(flight["departureDateTime"])
            date_str = dt.strftime("%Y-%m-%d")
            dep_time = dt.strftime("%H:%M")
            arr_dt = datetime.fromisoformat(flight["arrivalDateTime"])
            arr_time = arr_dt.strftime("%H:%M")

            origin = flight["departureAirportCode"]
            dest = flight["arrivalAirportCode"]
            url = build_ryanair_url(origin, dest, date_str)

            prices = price_cache.get((origin, dest, date_str), {})
            price = prices.get(dep_time)
            if price is None:
                for scraped_time, scraped_price in prices.items():
                    if scraped_time.strip() == dep_time:
                        price = scraped_price
                        break

            legs.append(LegPrice(origin=origin, destination=dest, date=date_str, departure_time=dep_time, arrival_time=arr_time, price=price, url=url))

            if price is not None:
                total += price
            else:
                all_found = False

        if all_found and legs:
            results.append(
                JourneyPrice(
                    legs=legs,
                    total_price=total,
                    total_duration=journey["duration"],
                    departure_datetime=journey["departureDateTime"],
                )
            )

    results.sort(key=lambda j: j.total_price)
    return results


def print_connections(connections: list[dict]):
    print(f"\n{'=' * 60}")
    print(f"AVAILABLE CONNECTIONS ({len(connections)} found)")
    print(f"{'=' * 60}\n")

    for i, j in enumerate(connections, 1):
        route = " -> ".join(f["departureAirportCode"] for f in j["flights"]) + f" -> {j['flights'][-1]['arrivalAirportCode']}"
        print(f"  {i:3d}. {route}  |  {j['departureDateTime'][:16]}  |  {j['duration']}")


def print_results(results: list[JourneyPrice], top: int):
    showing = min(top, len(results))
    print(f"\n{'=' * 60}")
    print(f"TOP {showing} CHEAPEST JOURNEYS")
    print(f"{'=' * 60}")

    for i, jp in enumerate(results[:top], 1):
        print(f"\n{'─' * 55}")
        print(f"  #{i}  TOTAL: £{jp.total_price:.2f}  |  Duration: {jp.total_duration}")
        print(f"      Departs: {jp.departure_datetime[:16]}")
        print(f"{'─' * 55}")
        for leg in jp.legs:
            print(f"  {leg.origin} -> {leg.destination}  |  {leg.date}  {leg.departure_time}-{leg.arrival_time}  |  £{leg.price:.2f}")
            print(f"  {leg.url}")


def serialize_connections(connections: list[dict]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for i, j in enumerate(connections, 1):
        route = " -> ".join(f["departureAirportCode"] for f in j["flights"]) + f" -> {j['flights'][-1]['arrivalAirportCode']}"
        items.append(
            {
                "rank": i,
                "route": route,
                "departure": j["departureDateTime"],
                "duration": j["duration"],
                "flights": j["flights"],
            }
        )
    return items


def serialize_results(results: list[JourneyPrice], top: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for i, jp in enumerate(results[:top], 1):
        output.append(
            {
                "rank": i,
                "total_price": jp.total_price,
                "duration": jp.total_duration,
                "departure": jp.departure_datetime,
                "legs": [
                    {
                        "route": f"{l.origin} -> {l.destination}",
                        "date": l.date,
                        "times": f"{l.departure_time}-{l.arrival_time}",
                        "price": l.price,
                        "url": l.url,
                    }
                    for l in jp.legs
                ],
            }
        )
    return output




def sanitize_output_filename(path: str) -> str:
    filename = Path(path).name
    if filename in {"", ".", ".."}:
        raise ValueError("Output file must be a valid filename")
    return filename


def save_results(results: list[JourneyPrice], path: str, top: int):
    output = serialize_results(results, top)
    safe_filename = sanitize_output_filename(path)

    with open(safe_filename, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to {safe_filename}")


def run_scraper(
    *,
    origin: str,
    destination: str,
    date_from: str | None = None,
    date_to: str | None = None,
    top: int = 5,
    no_scrape: bool = False,
    input_file: str | None = None,
    input_data: list[dict] | None = None,
    output_file: str = "cheapest_flights.json",
    no_headless: bool = False,
    layover_min: int = 1,
    layover_max: int = 8,
    save_output: bool = True,
) -> dict[str, Any]:
    date_from, date_to = resolve_dates(date_from, date_to)

    origin = origin.upper()
    destination = destination.upper()

    if input_data is not None and input_file:
        raise ValueError("Provide either input_data or input_file, not both")

    if input_data is not None:
        connections = input_data
    elif input_file:
        print(f"Loading connections from {input_file}...")
        connections = json.loads(Path(input_file).read_text())
        print(f"Loaded {len(connections)} connections\n")
    else:
        connections = fetch_connections(origin, destination, date_from, date_to, layover_min, layover_max)

    if not connections:
        raise ValueError("No connections found.")

    payload: dict[str, Any] = {
        "origin": origin,
        "destination": destination,
        "date_from": date_from,
        "date_to": date_to,
        "connections_count": len(connections),
    }

    if no_scrape:
        payload["mode"] = "connections"
        payload["connections"] = serialize_connections(connections)
        return payload

    unique_legs = get_unique_legs(connections)
    headless = not no_headless
    price_cache = asyncio.run(scrape_all_prices(unique_legs, headless))
    results = match_prices(connections, price_cache)

    if not results:
        raise ValueError("No complete price data found for any journey. Try --no-scrape to see available connections.")

    payload["mode"] = "priced"
    payload["priced_journeys"] = len(results)
    payload["results"] = serialize_results(results, top)

    if save_output:
        save_results(results, output_file, top)

    return payload


def main():
    args = parse_args()

    try:
        payload = run_scraper(
            origin=args.origin,
            destination=args.destination,
            date_from=args.date_from,
            date_to=args.date_to,
            top=args.top,
            no_scrape=args.no_scrape,
            input_file=args.input_file,
            output_file=args.output_file,
            no_headless=args.no_headless,
            layover_min=args.layover_min,
            layover_max=args.layover_max,
            save_output=not args.no_scrape,
        )
    except ValueError as exc:
        print(str(exc))
        sys.exit(1)

    if payload["mode"] == "connections":
        connections = payload["connections"]
        print_connections([{"flights": c["flights"], "departureDateTime": c["departure"], "duration": c["duration"]} for c in connections])
        return

    results = [
        JourneyPrice(
            legs=[
                LegPrice(
                    origin=leg["route"].split(" -> ")[0],
                    destination=leg["route"].split(" -> ")[1],
                    date=leg["date"],
                    departure_time=leg["times"].split("-")[0],
                    arrival_time=leg["times"].split("-")[1],
                    price=leg["price"],
                    url=leg["url"],
                )
                for leg in item["legs"]
            ],
            total_price=item["total_price"],
            total_duration=item["duration"],
            departure_datetime=item["departure"],
        )
        for item in payload["results"]
    ]

    print_results(results, args.top)
    print(f"\nPriced {payload['priced_journeys']} / {payload['connections_count']} journeys")


if __name__ == "__main__":
    main()
