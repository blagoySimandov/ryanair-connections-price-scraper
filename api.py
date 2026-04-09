import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from main import run_scraper_async

app = FastAPI(title="Ryanair Connections Price Scraper")


class _QueueWriter:
    def __init__(self, queue: "asyncio.Queue[dict[str, Any] | None]"):
        self.queue = queue
        self._buffer = ""

    def write(self, data: str) -> int:
        if not data:
            return 0
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                self.queue.put_nowait({"type": "log", "message": line})
        return len(data)

    def flush(self) -> None:
        line = self._buffer.strip()
        if line:
            self.queue.put_nowait({"type": "log", "message": line})
        self._buffer = ""


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

    should_save_results = not no_scrape

    try:
        payload = await run_scraper_async(
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
            save_output=should_save_results,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return payload


@app.post("/api/run/stream")
async def run_search_stream(
    origin: str = Form(...),
    destination: str = Form(...),
    date_from: str | None = Form(default=None),
    date_to: str | None = Form(default=None),
    top: int = Form(default=5),
    no_scrape: bool = Form(default=False),
    no_headless: bool = Form(default=False),
    layover_min: int = Form(default=1),
    layover_max: int = Form(default=8),
):
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    writer = _QueueWriter(queue)

    async def run_and_emit() -> None:
        try:
            with contextlib.redirect_stdout(writer):
                payload = await run_scraper_async(
                    origin=origin,
                    destination=destination,
                    date_from=date_from or None,
                    date_to=date_to or None,
                    top=top,
                    no_scrape=no_scrape,
                    input_data=None,
                    no_headless=no_headless,
                    layover_min=layover_min,
                    layover_max=layover_max,
                    save_output=not no_scrape,
                )
            await queue.put({"type": "result", "payload": payload})
        except ValueError as exc:
            await queue.put({"type": "error", "detail": str(exc)})
        except Exception as exc:
            await queue.put({"type": "error", "detail": str(exc)})
        finally:
            writer.flush()
            await queue.put(None)

    task = asyncio.create_task(run_and_emit())

    async def stream():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"
        await task

    return StreamingResponse(stream(), media_type="application/x-ndjson")


web_dist = Path(__file__).parent / "web" / "dist"
if web_dist.exists():
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")
