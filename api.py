import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from main import run_scraper

app = FastAPI(title="Ryanair Connections Price Scraper")


@app.post("/api/run")
async def run_search(
    origin: str = Form(...),
    destination: str = Form(...),
    date_from: str | None = Form(default=None),
    date_to: str | None = Form(default=None),
    top: int = Form(default=5),
    no_scrape: bool = Form(default=False),
    output_file: str = Form(default="cheapest_flights.json"),
    no_headless: bool = Form(default=False),
    layover_min: int = Form(default=1),
    layover_max: int = Form(default=8),
    input_file: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    input_data = None

    if input_file is not None:
        try:
            raw = await input_file.read()
            input_data = json.loads(raw.decode("utf-8"))
            if not isinstance(input_data, list):
                raise ValueError("Uploaded JSON must contain a list of connections")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid input JSON file: {exc}") from exc

    try:
        payload = run_scraper(
            origin=origin,
            destination=destination,
            date_from=date_from or None,
            date_to=date_to or None,
            top=top,
            no_scrape=no_scrape,
            input_data=input_data,
            output_file=output_file,
            no_headless=no_headless,
            layover_min=layover_min,
            layover_max=layover_max,
            save_output=not no_scrape,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return payload


web_dist = Path(__file__).parent / "web" / "dist"
if web_dist.exists():
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")
