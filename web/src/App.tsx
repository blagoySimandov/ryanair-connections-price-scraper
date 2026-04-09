import { useMemo, useRef, useState } from "react"
import { LoaderCircle } from "lucide-react"

import { Button } from "./components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "./components/ui/card"
import { Checkbox } from "./components/ui/checkbox"
import { Input } from "./components/ui/input"
import { Label } from "./components/ui/label"

type ConnectionItem = {
  rank: number
  route: string
  departure: string
  duration: string
}

type ResultLeg = {
  route: string
  date: string
  times: string
  price: number
  url: string
}

type ResultItem = {
  rank: number
  total_price: number
  duration: string
  departure: string
  legs: ResultLeg[]
}

type ApiResponse = {
  mode: "connections" | "priced"
  connections_count: number
  priced_journeys?: number
  connections?: ConnectionItem[]
  results?: ResultItem[]
}

type StreamEvent =
  | { type: "log"; message: string }
  | { type: "result"; payload: ApiResponse }
  | { type: "error"; detail: string }

type ProgressLog = {
  id: number
  message: string
}

const DATETIME_DISPLAY_LENGTH = 16
const HEADER_ICON_URL = "https://cdn-icons-png.flaticon.com/512/149/149059.png"
const DOWNLOAD_FILENAME = "cheapest_flights.json"

function App() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<ApiResponse | null>(null)
  const [progressLogs, setProgressLogs] = useState<ProgressLog[]>([])
  const progressIdRef = useRef(0)
  const [noScrape, setNoScrape] = useState(false)
  const [noHeadless, setNoHeadless] = useState(false)

  const [form, setForm] = useState({
    origin: "ORK",
    destination: "SOF",
    dateFrom: "",
    dateTo: "",
    top: "5",
    layoverMin: "1",
    layoverMax: "8",
  })

  const outputData = useMemo(() => {
    if (!response || response.mode !== "priced") return null
    return JSON.stringify(response.results ?? [], null, 2)
  }, [response])

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    setProgressLogs([])
    setResponse(null)

    try {
      const body = new FormData()
      body.set("origin", form.origin.trim().toUpperCase())
      body.set("destination", form.destination.trim().toUpperCase())
      body.set("date_from", form.dateFrom)
      body.set("date_to", form.dateTo)
      body.set("top", form.top)
      body.set("layover_min", form.layoverMin)
      body.set("layover_max", form.layoverMax)
      body.set("no_scrape", String(noScrape))
      body.set("no_headless", String(noHeadless))

      const res = await fetch("/api/run/stream", {
        method: "POST",
        body,
      })
      if (!res.ok || !res.body) {
        const payload = await res.json().catch(() => ({}))
        throw new Error(payload.detail ?? "Request failed")
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      let receivedResult = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""

        for (const line of lines) {
          if (!line.trim()) continue
          const eventData = JSON.parse(line) as StreamEvent
          if (eventData.type === "log") {
            progressIdRef.current += 1
            setProgressLogs((logs) => [...logs, { id: progressIdRef.current, message: eventData.message }])
            continue
          }
          if (eventData.type === "result") {
            receivedResult = true
            setResponse(eventData.payload)
            continue
          }
          throw new Error(eventData.detail || "Request failed")
        }
      }

      if (!receivedResult) {
        throw new Error("Streaming ended before a final result was received")
      }
    } catch (e) {
      setResponse(null)
      setError(e instanceof Error ? e.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  const onDownload = () => {
    if (!outputData) return
    const blob = new Blob([outputData], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = DOWNLOAD_FILENAME
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <main className="mx-auto max-w-5xl p-4 md:p-8">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <img src={HEADER_ICON_URL} alt="Flaticon logo" className="h-8 w-8 rounded-sm" />
            <CardTitle>Ryanair Connections Price Scraper</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="origin">Origin</Label>
              <Input id="origin" value={form.origin} onChange={(e) => setForm((f) => ({ ...f, origin: e.target.value }))} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="destination">Destination</Label>
              <Input id="destination" value={form.destination} onChange={(e) => setForm((f) => ({ ...f, destination: e.target.value }))} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dateFrom">From date</Label>
              <Input id="dateFrom" type="date" value={form.dateFrom} onChange={(e) => setForm((f) => ({ ...f, dateFrom: e.target.value }))} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dateTo">To date</Label>
              <Input id="dateTo" type="date" value={form.dateTo} onChange={(e) => setForm((f) => ({ ...f, dateTo: e.target.value }))} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="top">Top results</Label>
              <Input id="top" type="number" min="1" value={form.top} onChange={(e) => setForm((f) => ({ ...f, top: e.target.value }))} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="layoverMin">Layover min (hours)</Label>
              <Input id="layoverMin" type="number" min="0" value={form.layoverMin} onChange={(e) => setForm((f) => ({ ...f, layoverMin: e.target.value }))} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="layoverMax">Layover max (hours)</Label>
              <Input id="layoverMax" type="number" min="1" value={form.layoverMax} onChange={(e) => setForm((f) => ({ ...f, layoverMax: e.target.value }))} />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="noScrape" checked={noScrape} onCheckedChange={(v) => setNoScrape(Boolean(v))} />
              <Label htmlFor="noScrape">No scrape (list connections only)</Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="noHeadless" checked={noHeadless} onCheckedChange={(v) => setNoHeadless(Boolean(v))} />
              <Label htmlFor="noHeadless">No headless browser</Label>
            </div>
            <div className="md:col-span-2 flex flex-wrap gap-2">
              <Button type="submit" disabled={loading}>
                {loading ? <LoaderCircle className="size-4 animate-spin" /> : null}
                Run scraper
              </Button>
              {outputData && (
                <Button type="button" variant="outline" onClick={onDownload}>
                  Download results JSON
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      {error && (
        <Card className="mt-4 border-red-200">
          <CardContent>
            <p className="text-sm text-red-700">{error}</p>
          </CardContent>
        </Card>
      )}

      {(loading || progressLogs.length > 0) && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Realtime progress</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-72 overflow-auto rounded-md border bg-slate-50 p-3 text-xs text-slate-700">
              {progressLogs.length === 0 ? "Starting scraper..." : progressLogs.map((log) => <div key={log.id}>{log.message}</div>)}
            </div>
          </CardContent>
        </Card>
      )}

      {response && response.mode === "connections" && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Connections ({response.connections_count})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(response.connections ?? []).map((item) => (
                <div key={`${item.rank}-${item.route}-${item.departure}`} className="rounded-md border p-3 text-sm">
                  <div className="font-medium">#{item.rank} {item.route}</div>
                  <div className="text-slate-600">Departure: {item.departure.slice(0, DATETIME_DISPLAY_LENGTH)} | Duration: {item.duration}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {response && response.mode === "priced" && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>
              Cheapest journeys ({response.results?.length ?? 0}) from {response.connections_count} connections
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {(response.results ?? []).map((item) => (
                <div key={item.rank} className="rounded-md border p-3 text-sm">
                  <div className="font-medium">
                    #{item.rank} | £{item.total_price.toFixed(2)} | {item.duration} | {item.departure.slice(0, DATETIME_DISPLAY_LENGTH)}
                  </div>
                  <ul className="mt-2 space-y-1">
                    {item.legs.map((leg) => (
                      <li key={`${item.rank}-${leg.route}-${leg.times}`}>
                        {leg.route} | {leg.date} {leg.times} | £{leg.price.toFixed(2)} | <a className="underline" href={leg.url} target="_blank" rel="noreferrer">link</a>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </main>
  )
}

export default App
