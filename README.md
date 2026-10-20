# RideWise

AI ride planner for motorcyclists: route, weather window, fuel stops and gear checklist, built on LangGraph, LiteLLM and Langfuse.

You say *"twisty backroads this Saturday, about 250 km, home before dark"*. RideWise builds several loops from your doorstep, works out which departure time keeps you ahead of the rain, places fuel stops your bike can actually reach, and writes a gear list for the weather you will meet.

## What makes it more than a route drawer

**It picks the loop, you don't.** There is no destination to type. RideWise generates candidate loops in four directions, routes each one, and scores them on *twistiness* — the average heading change per kilometre, measured from the returned geometry. A motorway scores near 0; a mountain pass runs 60 or more.

**The weather window is ETA-aware.** A forecast for the day is not much use on a 250 km loop: leaving at 09:00 instead of 13:00 can put you at the far side either side of a front. RideWise samples points along the route, works out when you would reach each one, and scores the weather *there, then*. The worst stretch is weighted deliberately — one hour of hail ruins an otherwise sunny ride — so the score is `0.6 × mean + 0.4 × worst`.

**Fuel is your bike's problem, not a generic one.** Range comes from your tank minus the reserve you keep, times a safety margin, so plans never assume you ride on the reserve light. If a stretch has no reachable station, it says so instead of quietly omitting it.

**It degrades instead of failing.** No LLM key still gets you route, weather and fuel — only the gear list and briefing drop out, each with a warning saying why.

## Setup

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/), and Node 18+ for the web app.

```bash
make install                 # uv sync --extra dev, then npm install in web/
cp .env.example .env
uv run python -m ridewise.seed   # a starter garage and home base
```

Then edit `.env`:

| Variable | Needed? | Notes |
| --- | --- | --- |
| `RIDEWISE_ORS_API_KEY` | **yes** | Routing and geocoding. Free key: [openrouteservice.org/dev/#/signup](https://openrouteservice.org/dev/#/signup) |
| `ANTHROPIC_API_KEY` | for gear + briefing | Or any other provider key LiteLLM supports |
| `RIDEWISE_LLM_MODEL` | no | Defaults to `anthropic/claude-opus-5-5` |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | no | Tracing is skipped silently when unset |

No key is needed for weather ([Open-Meteo](https://open-meteo.com)) or fuel stations ([Overpass](https://overpass-api.de)).

## Running it

Two processes in development — the API on :8000 and Vite on :5173, which proxies
`/api` to it:

```bash
make api      # uvicorn, port 8000
make web      # vite, port 5173  → open this one
```

Four screens, in a line: **log in**, **your motorcycle** (with a photo),
**ask**, **options**. The planner takes about ten seconds and the Ask screen
streams its eight steps over server-sent events while you wait.

For a single process, build the frontend and let the API serve it:

```bash
make build
make api      # now also serves web/dist at /
```

> **Accounts are not implemented.** The login screen remembers a name in
> `localStorage` and nothing else — there is no password, no session and no
> per-user data. Everything is one shared garage. See issue #14.

The original Streamlit UI is still here and still works (`make run`); it is the
quickest way to see a plan without the frontend. There is a CLI too, which is
the quickest way to iterate on the graph:

```bash
uv run ridewise plan "twisty backroads Saturday, 250 km, back before dark"
uv run ridewise plan --from Lviv --km 300 --bike Tenere --date 2026-10-25
uv run ridewise garage
```

## How it fits together

```
                 ┌──────── LangGraph pipeline ────────┐
free text ──────►│ intake    LLM → geocode            │
                 │ routes    4 loops, scored on roads │──► OpenRouteService
                 │ weather   one batched forecast call│──► Open-Meteo
                 │ choose    roads × weather          │
                 │ fuel      stations your tank reaches│─► Overpass / OSM
                 │ gear      LLM, structured          │
                 │ briefing  LLM, prose               │
                 │ assemble                           │
                 └────────────────┬───────────────────┘
                                  ▼
                               RidePlan ──► Streamlit + folium
```

| Module | Does |
| --- | --- |
| `geo.py` | Geodesy. Loop ring construction, twistiness, interpolation along a path. Pure stdlib, no I/O. |
| `planner.py` | Scoring and selection. Rideability, weather windows, route quality. No LLM calls. |
| `providers/` | ORS routing + geocoding, Open-Meteo forecast, Overpass fuel stations. |
| `agent/` | The LangGraph graph, its state, and the nodes. |
| `llm.py` | LiteLLM access and schema-validated JSON. |
| `models.py` | SQLModel garage tables and the Pydantic plan types. |
| `api.py` | FastAPI over `plan_ride`, plus garage CRUD and photo upload. Thin by design. |
| `ui/` | The original Streamlit pages and the folium map. |
| `web/` | React + TypeScript frontend. `screens/` is one file per screen. |

### Three decisions worth knowing about

**Loops are built geometrically, not with ORS round-trip.** ORS can generate round trips, but the public plan [caps them at 100 km](https://openrouteservice.org/restrictions/) — too short for a day ride. So RideWise places a ring of waypoints around the start and asks for ordinary directions through them (capped at 6000 km / 50 waypoints instead), refining the ring radius against the distance actually returned. The bonus: we control the shape, so we can generate candidates in different directions and compare them.

**Structured output is prompt-and-validate, not `response_format`.** LiteLLM implements JSON schema for Anthropic by forcing a tool call, and `tool_choice: tool|any` is rejected with a 400 on Claude Opus 5.5 and Sonnet 5.5. Asking for JSON in the prompt and validating with Pydantic — retrying once with the validation error attached — works on every provider LiteLLM can reach, which is the whole reason for routing through it.

**No sampling parameters are sent.** Those same models reject `temperature` and `top_p` with a 400. `RIDEWISE_LLM_TEMPERATURE` exists for pointing at older models and is unset by default.

## Tests

```bash
make test        # 71 tests, no network, no API keys
make lint
make typecheck
```

Everything external is mocked: `respx` for the HTTP providers, stubs for the LLM. `tests/test_graph_integration.py` runs the whole graph end to end — including a fixture where it rains from 15:00, asserting the planner picks a morning departure — `tests/test_ui_smoke.py` renders every Streamlit page headlessly through `AppTest`, and
`tests/test_db.py` covers the detached-instance save path the API exercises.

The frontend is typechecked, not unit-tested yet:

```bash
cd web && npm run build      # tsc --noEmit, then vite build
```

## Not built yet

One rider, one good plan, one web app. The tracked work is in
[the issues](https://github.com/AndrewKarpaty/RideWise/issues); the gaps the
frontend makes most obvious are:

- **Accounts** (#14) — the login screen is a local stub.
- **GPX export** (#2) — nothing yet carries a plan to the device you navigate with.
- **Saving a plan** — `SavedPlan` exists in the database but has no API route, so
  the Options screen cannot keep one.
- **A real basemap** — `RouteMap` draws the routed geometry as an SVG with no
  tiles. Swapping in MapLibre means replacing that one component.
- **Sunset** (#3) and the **curviness dial** (#7) are designed but not wired.
