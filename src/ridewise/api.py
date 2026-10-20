"""HTTP API over the planner, for the React frontend in `web/`.

Deliberately thin: it validates input, calls the same `plan_ride` the CLI uses,
and serialises the result. No planning logic lives here.

Run it with `make api` (uvicorn on :8000). The dev frontend on :5173 proxies
`/api` here, so there is no CORS to think about in development; the allowed
origins below exist for the case where the two are served from different hosts.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Iterator
from datetime import date
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ridewise.agent.graph import NODE_LABELS, plan_ride_stream
from ridewise.agent.nodes import PlannerFailure
from ridewise.config import PROJECT_ROOT, get_settings
from ridewise.db import (
    delete_motorcycle,
    get_motorcycle,
    get_profile,
    list_motorcycles,
    save_motorcycle,
    save_profile,
)
from ridewise.llm import LLMError
from ridewise.models import (
    BikeCategory,
    Experience,
    Motorcycle,
    RidePlan,
    TireType,
    WindProtection,
)
from ridewise.providers.routing import RoutingError

logger = logging.getLogger(__name__)

UPLOAD_DIR = PROJECT_ROOT / "uploads"
MAX_PHOTO_BYTES = 8 * 1024 * 1024
PHOTO_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

app = FastAPI(title="RideWise API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ---------------------------------------------------------------------------
# wire formats
# ---------------------------------------------------------------------------


class BikeIn(BaseModel):
    """A motorcycle as the browser sends it."""

    nickname: str = Field(min_length=1, max_length=60)
    make: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=80)
    year: int | None = Field(default=None, ge=1900, le=2100)
    category: BikeCategory = BikeCategory.NAKED
    tank_liters: float = Field(gt=0, le=80)
    consumption_l_per_100km: float = Field(gt=0, le=30)
    reserve_liters: float = Field(default=2.0, ge=0, le=20)
    wind_protection: WindProtection = WindProtection.LOW
    tire_type: TireType = TireType.ROAD
    heated_grips: bool = False
    has_luggage: bool = False
    notes: str = Field(default="", max_length=2000)
    is_default: bool = False


class BikeOut(BikeIn):
    id: int
    photo_url: str | None = None
    range_km: float
    label: str

    @classmethod
    def of(cls, bike: Motorcycle) -> BikeOut:
        return cls(
            id=bike.id or 0,
            nickname=bike.nickname,
            make=bike.make,
            model=bike.model,
            year=bike.year,
            category=bike.category,
            tank_liters=bike.tank_liters,
            consumption_l_per_100km=bike.consumption_l_per_100km,
            reserve_liters=bike.reserve_liters,
            wind_protection=bike.wind_protection,
            tire_type=bike.tire_type,
            heated_grips=bike.heated_grips,
            has_luggage=bike.has_luggage,
            notes=bike.notes,
            is_default=bike.is_default,
            photo_url=f"/uploads/{bike.photo_path}" if bike.photo_path else None,
            range_km=round(bike.range_km, 1),
            label=bike.label,
        )


class ProfileIn(BaseModel):
    name: str = Field(default="Rider", max_length=80)
    home_label: str = Field(default="", max_length=200)
    experience: Experience = Experience.INTERMEDIATE
    min_comfortable_temp_c: float = Field(default=8.0, ge=-30, le=40)
    accepts_rain: bool = False


class ProfileOut(ProfileIn):
    id: int


class PlanIn(BaseModel):
    """A ride request. `prompt` is the free text; the rest are the fallbacks."""

    prompt: str = Field(default="", max_length=2000)
    bike_id: int | None = None
    start_place: str = Field(default="", max_length=200)
    distance_km: float = Field(default=250, ge=20, le=1200)
    ride_date: date | None = None
    earliest: str = "08:00"
    latest: str = "19:00"
    avoid_highways: bool = True
    prefer_twisty: bool = True


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _apply(bike: Motorcycle, payload: BikeIn) -> Motorcycle:
    for field, value in payload.model_dump().items():
        setattr(bike, field, value)
    return bike


def _resolve_bike(bike_id: int | None) -> Motorcycle:
    if bike_id is not None:
        bike = get_motorcycle(bike_id)
        if bike is None:
            raise HTTPException(404, f"No motorcycle with id {bike_id}")
        return bike
    bikes = list_motorcycles()
    if not bikes:
        raise HTTPException(409, "Your garage is empty — add a motorcycle before planning a ride.")
    return bikes[0]


def _planner_kwargs(payload: PlanIn) -> dict[str, Any]:
    bike = _resolve_bike(payload.bike_id)
    profile = get_profile()
    return {
        "raw_request": payload.prompt,
        "bike": bike,
        "profile": profile,
        "start_place": payload.start_place or profile.home_label,
        "distance_km": payload.distance_km,
        "ride_date": payload.ride_date or date.today(),
        "earliest": payload.earliest,
        "latest": payload.latest,
        "avoid_highways": payload.avoid_highways,
        "prefer_twisty": payload.prefer_twisty,
    }


def _as_http_error(exc: Exception) -> HTTPException:
    """Turn a planner failure into something the UI can show a rider."""
    if isinstance(exc, PlannerFailure):
        return HTTPException(422, str(exc))
    if isinstance(exc, RoutingError):
        return HTTPException(503, str(exc))
    if isinstance(exc, LLMError):
        return HTTPException(503, f"The language model is unavailable: {exc}")
    logger.exception("unexpected planner error")
    return HTTPException(500, "The planner failed unexpectedly. Check the server log.")


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "ok": True,
        "routing_configured": bool(settings.ors_api_key),
        "model": settings.llm_model,
    }


@app.get("/api/bikes")
def read_bikes() -> list[BikeOut]:
    return [BikeOut.of(b) for b in list_motorcycles()]


@app.post("/api/bikes", status_code=201)
def create_bike(payload: BikeIn) -> BikeOut:
    bike = _apply(
        Motorcycle(nickname="", make="", model="", tank_liters=1, consumption_l_per_100km=1),
        payload,
    )
    return BikeOut.of(save_motorcycle(bike))


@app.put("/api/bikes/{bike_id}")
def update_bike(bike_id: int, payload: BikeIn) -> BikeOut:
    bike = get_motorcycle(bike_id)
    if bike is None:
        raise HTTPException(404, f"No motorcycle with id {bike_id}")
    return BikeOut.of(save_motorcycle(_apply(bike, payload)))


@app.delete("/api/bikes/{bike_id}", status_code=204)
def remove_bike(bike_id: int) -> None:
    bike = get_motorcycle(bike_id)
    if bike is None:
        raise HTTPException(404, f"No motorcycle with id {bike_id}")
    if bike.photo_path:
        (UPLOAD_DIR / bike.photo_path).unlink(missing_ok=True)
    delete_motorcycle(bike_id)


@app.post("/api/bikes/{bike_id}/photo")
def upload_photo(bike_id: int, file: Annotated[UploadFile, File()]) -> BikeOut:
    bike = get_motorcycle(bike_id)
    if bike is None:
        raise HTTPException(404, f"No motorcycle with id {bike_id}")

    suffix = PHOTO_TYPES.get(file.content_type or "")
    if suffix is None:
        raise HTTPException(415, "Photos must be JPEG, PNG or WebP.")

    # Trust the declared type only so far: cap what we are willing to copy.
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_PHOTO_BYTES:
        raise HTTPException(413, f"That photo is {size // 1024 // 1024} MB; the limit is 8 MB.")

    # The name is derived from the row id, never from the uploaded filename.
    target = UPLOAD_DIR / f"bike-{bike_id}{suffix}"
    for stale in UPLOAD_DIR.glob(f"bike-{bike_id}.*"):
        stale.unlink(missing_ok=True)
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)

    bike.photo_path = target.name
    return BikeOut.of(save_motorcycle(bike))


@app.delete("/api/bikes/{bike_id}/photo")
def remove_photo(bike_id: int) -> BikeOut:
    bike = get_motorcycle(bike_id)
    if bike is None:
        raise HTTPException(404, f"No motorcycle with id {bike_id}")
    if bike.photo_path:
        (UPLOAD_DIR / bike.photo_path).unlink(missing_ok=True)
        bike.photo_path = None
        bike = save_motorcycle(bike)
    return BikeOut.of(bike)


@app.get("/api/profile")
def read_profile() -> ProfileOut:
    profile = get_profile()
    return ProfileOut(
        id=profile.id or 0,
        name=profile.name,
        home_label=profile.home_label,
        experience=profile.experience,
        min_comfortable_temp_c=profile.min_comfortable_temp_c,
        accepts_rain=profile.accepts_rain,
    )


@app.put("/api/profile")
def write_profile(payload: ProfileIn) -> ProfileOut:
    profile = get_profile()
    for field, value in payload.model_dump().items():
        setattr(profile, field, value)
    saved = save_profile(profile)
    return ProfileOut(
        id=saved.id or 0,
        name=saved.name,
        home_label=saved.home_label,
        experience=saved.experience,
        min_comfortable_temp_c=saved.min_comfortable_temp_c,
        accepts_rain=saved.accepts_rain,
    )


@app.post("/api/plan")
def create_plan(payload: PlanIn) -> RidePlan:
    """Plan a ride and wait for the whole thing. Takes roughly ten seconds."""
    kwargs = _planner_kwargs(payload)
    plan: RidePlan | None = None
    try:
        for _, update in plan_ride_stream(**kwargs):
            if "plan" in update:
                plan = update["plan"]
    except Exception as exc:
        raise _as_http_error(exc) from exc

    if plan is None:
        raise HTTPException(500, "The planner finished without producing a plan.")
    return plan


@app.post("/api/plan/stream")
def stream_plan(payload: PlanIn) -> StreamingResponse:
    """The same plan, as server-sent events, so the UI can show progress.

    Events: `progress` per finished node, then one `plan`, or `error`.
    """
    kwargs = _planner_kwargs(payload)

    def events() -> Iterator[str]:
        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        try:
            for node, update in plan_ride_stream(**kwargs):
                yield sse(
                    "progress",
                    {
                        "node": node,
                        "label": NODE_LABELS.get(node, node),
                        "lines": update.get("progress", []),
                    },
                )
                if "plan" in update:
                    yield sse("plan", json.loads(update["plan"].model_dump_json()))
        except Exception as exc:
            error = _as_http_error(exc)
            yield sse("error", {"status": error.status_code, "detail": error.detail})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Serve the built frontend when it exists, so `uvicorn ridewise.api:app` alone
# is enough in production. In development Vite serves it on :5173 instead.
_DIST = PROJECT_ROOT / "web" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")
