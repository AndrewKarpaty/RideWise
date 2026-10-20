"""Graph nodes. Each one takes the state and returns only the keys it changed."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel, Field

from ridewise import prompts
from ridewise.agent.state import PlannerState
from ridewise.config import get_settings
from ridewise.geo import sample_along
from ridewise.llm import LLMError, chat, chat_json
from ridewise.models import (
    FuelStop,
    GearItem,
    RidePlan,
    RideRequest,
    RouteCandidate,
    WeatherWindow,
)
from ridewise.planner import best_windows, combined_score, elapsed_hours, score_route
from ridewise.providers.fuel import plan_fuel_stops
from ridewise.providers.routing import FAST_AVOID, TWISTY_AVOID, RoutingClient, RoutingError
from ridewise.providers.weather import WeatherClient, WeatherError, describe_code

logger = logging.getLogger(__name__)

# Open-Meteo publishes 16 days ahead.
FORECAST_HORIZON_DAYS = 16


class PlannerFailure(RuntimeError):
    """The planner cannot produce any plan at all."""


# ---------------------------------------------------------------------------
# intake
# ---------------------------------------------------------------------------


class _Intake(BaseModel):
    """What the model extracts from free text."""

    start_place: str = Field(description="A geocodable place name to start from")
    target_distance_km: float = Field(description="Total loop length in kilometres")
    ride_date: str = Field(description="Ride date as YYYY-MM-DD")
    earliest_departure: str = Field(default="08:00", description="HH:MM, 24-hour")
    latest_return: str = Field(default="19:00", description="HH:MM, 24-hour")
    avoid_highways: bool = True
    prefer_twisty: bool = True
    notes: str = ""


def _parse_time(value: str | None, fallback: time) -> time:
    if not value:
        return fallback
    for fmt in ("%H:%M", "%H:%M:%S", "%H.%M"):
        try:
            return datetime.strptime(value.strip(), fmt).time()
        except ValueError:
            continue
    return fallback


def _parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return fallback


def intake(state: PlannerState) -> dict:
    """Normalise the request, using the LLM only when there is free text to read."""
    today = state.get("today") or date.today()
    raw = (state.get("raw_request") or "").strip()

    start_place = state.get("form_start_place") or ""
    distance_km = float(state.get("form_distance_km") or 250)
    ride_date = state.get("form_ride_date") or today
    earliest = _parse_time(state.get("form_earliest"), time(8, 0))
    latest = _parse_time(state.get("form_latest"), time(19, 0))
    avoid_highways = bool(state.get("form_avoid_highways", True))
    prefer_twisty = bool(state.get("form_prefer_twisty", True))
    notes = ""

    warnings: list[str] = []

    # Short strings carry no information worth a model call ("ride", "ok").
    if len(raw) >= 8:
        profile = state.get("profile")
        home = getattr(profile, "home_label", "") or ""
        context = (
            f"Current date: {today.isoformat()} ({today.strftime('%A')}).\n"
            f"Rider's home base: {home or 'unknown'}.\n"
            f"Defaults if the rider does not say: start_place={start_place or home!r}, "
            f"target_distance_km={distance_km}, ride_date={ride_date.isoformat()}, "
            f"earliest_departure={earliest.strftime('%H:%M')}, "
            f"latest_return={latest.strftime('%H:%M')}.\n\n"
            f"Ride request: {raw}"
        )
        try:
            parsed = chat_json(
                [
                    {"role": "system", "content": prompts.INTAKE_SYSTEM},
                    {"role": "user", "content": context},
                ],
                _Intake,
                metadata={"ridewise_node": "intake"},
            )
            start_place = parsed.start_place or start_place
            distance_km = parsed.target_distance_km or distance_km
            ride_date = _parse_date(parsed.ride_date, ride_date)
            earliest = _parse_time(parsed.earliest_departure, earliest)
            latest = _parse_time(parsed.latest_return, latest)
            avoid_highways = parsed.avoid_highways
            prefer_twisty = parsed.prefer_twisty
            notes = parsed.notes
        except LLMError as exc:
            warnings.append(
                f"Could not interpret the free-text request, so the form values were used "
                f"instead ({exc})."
            )

    if not start_place:
        raise PlannerFailure("No starting point given - set one in the form or your profile.")

    # The model can return anything; keep it inside what RideRequest accepts.
    distance_km = min(max(distance_km, 20.0), 1200.0)
    if ride_date < today:
        warnings.append(f"Ride date {ride_date} is in the past; planning for {today} instead.")
        ride_date = today
    horizon = today + timedelta(days=FORECAST_HORIZON_DAYS)
    if ride_date > horizon:
        warnings.append(
            f"{ride_date} is beyond the {FORECAST_HORIZON_DAYS}-day forecast horizon, "
            "so the weather window will be unavailable."
        )
    if latest <= earliest:
        warnings.append(
            f"Return time {latest.strftime('%H:%M')} is not after departure "
            f"{earliest.strftime('%H:%M')}; using 19:00."
        )
        latest = time(19, 0)

    try:
        with RoutingClient() as routing:
            place = routing.geocode_one(start_place)
    except RoutingError as exc:
        raise PlannerFailure(f"Could not locate {start_place!r}: {exc}") from exc

    request = RideRequest(
        raw_text=raw,
        start=place,
        target_distance_km=distance_km,
        ride_date=ride_date,
        earliest_departure=earliest,
        latest_return=latest,
        avoid_highways=avoid_highways,
        prefer_twisty=prefer_twisty,
        notes=notes,
    )
    return {
        "request": request,
        "warnings": warnings,
        "progress": [
            f"Planning a {distance_km:.0f} km ride from {place.label} on "
            f"{ride_date.strftime('%a %d %b')}"
        ],
    }


# ---------------------------------------------------------------------------
# route candidates
# ---------------------------------------------------------------------------


def generate_candidates(state: PlannerState) -> dict:
    """Build several loops in different directions and score their roads."""
    request = state["request"]
    settings = get_settings()
    avoid = TWISTY_AVOID if request.avoid_highways else FAST_AVOID

    count = max(settings.candidate_count, 1)
    # Offset so a 4-candidate run does not always send the first loop due north.
    bearings = [(360 / count) * i + 25 for i in range(count)]

    candidates: list[RouteCandidate] = []
    warnings: list[str] = []

    with RoutingClient() as routing:
        for i, bearing in enumerate(bearings):
            try:
                candidate = routing.fit_loop(
                    request.start.point,
                    request.target_distance_km,
                    bearing,
                    candidate_id=f"c{i + 1}",
                    avoid_features=avoid,
                )
            except RoutingError as exc:
                warnings.append(f"No route found heading {bearing:.0f} degrees: {exc}")
                continue
            candidate.road_score = round(score_route(candidate, request), 1)
            candidates.append(candidate)

    if not candidates:
        raise PlannerFailure(
            "Could not build a single loop from there. Try a different starting point or distance."
        )

    candidates.sort(key=lambda c: c.road_score, reverse=True)
    best = candidates[0]
    return {
        "candidates": candidates,
        "warnings": warnings,
        "progress": [
            f"Found {len(candidates)} loop(s); best roads so far: {best.name} "
            f"({best.twistiness:.0f} deg/km, {best.ascent_m:.0f} m climbing)"
        ],
    }


# ---------------------------------------------------------------------------
# weather
# ---------------------------------------------------------------------------


def forecast_candidates(state: PlannerState) -> dict:
    """Forecast every candidate's sample points in a single Open-Meteo request."""
    request = state["request"]
    candidates = state["candidates"]
    profile = state["profile"]
    settings = get_settings()
    samples = max(settings.weather_sample_points, 2)

    per_candidate: list[list[tuple[float, float]]] = []
    all_points: list[tuple[float, float]] = []
    for candidate in candidates:
        points = [point for _, point in sample_along(candidate.geometry, samples)]
        per_candidate.append(points)
        all_points.extend(points)

    try:
        with WeatherClient() as weather:
            # One extra day in case a long loop runs past midnight.
            blocks = weather.forecast(
                all_points, request.ride_date, request.ride_date + timedelta(days=1)
            )
    except WeatherError as exc:
        return {
            "candidate_windows": {},
            "warnings": [f"Weather forecast unavailable: {exc}"],
            "progress": ["Skipped the weather window - forecast unavailable"],
        }

    windows: dict[str, list[WeatherWindow]] = {}
    cursor = 0
    for candidate in candidates:
        block = blocks[cursor : cursor + samples]
        cursor += samples
        windows[candidate.candidate_id] = best_windows(candidate, block, request, profile)

    best = max((w[0] for w in windows.values() if w), key=lambda w: w.score, default=None)
    progress = (
        f"Best weather window: depart {best.departure.strftime('%H:%M')} "
        f"(score {best.score:.0f}/100)"
        if best
        else "No departure time fits inside the chosen day"
    )
    return {"candidate_windows": windows, "progress": [progress]}


# ---------------------------------------------------------------------------
# choose
# ---------------------------------------------------------------------------


def choose_route(state: PlannerState) -> dict:
    """Rank candidates on roads and weather together, and pick one."""
    candidates = state["candidates"]
    windows = state.get("candidate_windows") or {}
    request = state["request"]

    def rank(candidate: RouteCandidate) -> float:
        options = windows.get(candidate.candidate_id) or []
        return combined_score(candidate.road_score, options[0] if options else None)

    ordered = sorted(candidates, key=rank, reverse=True)
    chosen = ordered[0]
    options = windows.get(chosen.candidate_id) or []

    warnings: list[str] = []
    needed = elapsed_hours(chosen)
    available = (
        datetime.combine(request.ride_date, request.latest_return)
        - datetime.combine(request.ride_date, request.earliest_departure)
    ).total_seconds() / 3600
    if needed > available:
        warnings.append(
            f"This loop needs about {needed:.1f} h including stops, but your day only "
            f"allows {available:.1f} h. Start earlier, or shorten the ride."
        )

    return {
        "route": chosen,
        "alternatives": ordered[1:],
        "weather": options[0] if options else None,
        "weather_options": options,
        "warnings": warnings,
        "progress": [f"Chose {chosen.name} (roads {chosen.road_score:.0f}/100)"],
    }


# ---------------------------------------------------------------------------
# fuel
# ---------------------------------------------------------------------------


def plan_fuel(state: PlannerState) -> dict:
    route = state["route"]
    bike = state["bike"]

    stops, warnings = plan_fuel_stops(route.geometry, bike)
    if stops:
        progress = f"{len(stops)} fuel stop(s) needed for {bike.range_km:.0f} km of range"
    else:
        progress = f"No fuel stop needed - {bike.label} covers {route.distance_km:.0f} km"
    return {"fuel_stops": stops, "warnings": warnings, "progress": [progress]}


# ---------------------------------------------------------------------------
# gear
# ---------------------------------------------------------------------------


class _GearList(BaseModel):
    items: list[GearItem]


def _ride_context(state: PlannerState) -> str:
    """The shared brief both LLM nodes read from."""
    request = state["request"]
    route = state["route"]
    bike = state["bike"]
    weather: WeatherWindow | None = state.get("weather")
    fuel: list[FuelStop] = state.get("fuel_stops") or []

    lines = [
        "RIDE",
        f"- Date: {request.ride_date.strftime('%A %d %B %Y')}",
        f"- Start/finish: {request.start.label}",
        f"- Loop: {route.distance_km:.0f} km heading {route.direction}, "
        f"{route.moving_duration_h:.1f} h moving, "
        f"about {elapsed_hours(route):.1f} h with stops",
        f"- Roads: {route.twistiness:.0f} degrees of turning per km, "
        f"{route.ascent_m:.0f} m climbing, "
        f"{'motorways avoided' if request.avoid_highways else 'motorways allowed'}",
        "",
        "MOTORCYCLE",
        f"- {bike.label}, a {bike.category.value}",
        f"- Tank {bike.tank_liters:.0f} L at {bike.consumption_l_per_100km:.1f} L/100 km "
        f"-> about {bike.range_km:.0f} km usable range",
        f"- Wind protection: {bike.wind_protection.value}; tyres: {bike.tire_type.value}; "
        f"heated grips: {'yes' if bike.heated_grips else 'no'}; "
        f"luggage: {'yes' if bike.has_luggage else 'no'}",
    ]
    if bike.notes:
        lines.append(f"- Rider's notes on the bike: {bike.notes}")

    lines += ["", "WEATHER"]
    if weather:
        lines += [
            f"- Depart {weather.departure.strftime('%H:%M')}, "
            f"back {weather.arrival.strftime('%H:%M')}",
            f"- Rideability {weather.score:.0f}/100 - {weather.verdict}",
            f"- Feels like {weather.min_temp_c:.0f} to {weather.max_temp_c:.0f} C, "
            f"rain risk up to {weather.rain_risk_pct:.0f}%, "
            f"{weather.total_precipitation_mm:.1f} mm expected, "
            f"gusts to {weather.max_gust_kmh:.0f} km/h",
            "- Along the route:",
        ]
        for leg in weather.legs:
            hour = leg.weather
            lines.append(
                f"  - km {leg.distance_along_km:.0f} at "
                f"{leg.eta.strftime('%H:%M')}: {describe_code(hour.weather_code)}, "
                f"{hour.temperature_c:.0f} C (feels {hour.apparent_temperature_c:.0f} C), "
                f"rain {hour.precipitation_probability:.0f}%, "
                f"gusts {hour.wind_gusts_kmh:.0f} km/h"
            )
    else:
        lines.append("- No forecast available for this date.")

    lines += ["", "FUEL"]
    if fuel:
        for stop in fuel:
            lines.append(f"- {stop.name} at km {stop.distance_along_km:.0f} ({stop.reason})")
    else:
        lines.append("- No refuelling stop needed on this loop.")

    if request.notes:
        lines += ["", f"RIDER'S OWN NOTES: {request.notes}"]
    warnings = state.get("warnings") or []
    if warnings:
        lines += ["", "KNOWN PROBLEMS"] + [f"- {w}" for w in warnings]

    return "\n".join(lines)


def build_gear_list(state: PlannerState) -> dict:
    context = _ride_context(state)
    try:
        result = chat_json(
            [
                {"role": "system", "content": prompts.GEAR_SYSTEM},
                {"role": "user", "content": context},
            ],
            _GearList,
            metadata={"ridewise_node": "gear"},
        )
    except LLMError as exc:
        return {
            "gear": [],
            "warnings": [f"Could not generate the gear checklist: {exc}"],
            "progress": ["Gear checklist skipped"],
        }
    return {
        "gear": result.items,
        "progress": [f"Gear checklist: {len(result.items)} items"],
    }


# ---------------------------------------------------------------------------
# briefing
# ---------------------------------------------------------------------------


def write_briefing(state: PlannerState) -> dict:
    context = _ride_context(state)
    gear = state.get("gear") or []
    if gear:
        essentials = ", ".join(item.item for item in gear if item.essential) or "none flagged"
        context += f"\n\nESSENTIAL GEAR ALREADY ON THE LIST: {essentials}"

    try:
        text = chat(
            [
                {"role": "system", "content": prompts.BRIEFING_SYSTEM},
                {"role": "user", "content": context},
            ],
            metadata={"ridewise_node": "briefing"},
            max_tokens=1200,
        )
    except LLMError as exc:
        return {
            "briefing": "",
            "warnings": [f"Could not write the ride briefing: {exc}"],
            "progress": ["Briefing skipped"],
        }
    return {"briefing": text, "progress": ["Briefing written"]}


# ---------------------------------------------------------------------------
# assemble
# ---------------------------------------------------------------------------


def assemble(state: PlannerState) -> dict:
    # Keep each candidate's best window so the plan can be shown as a set of
    # options, every one with its own departure time and score.
    windows = state.get("candidate_windows") or {}
    best_per_candidate = {
        candidate_id: options[0] for candidate_id, options in windows.items() if options
    }

    plan = RidePlan(
        request=state["request"],
        bike_label=state["bike"].label,
        route=state["route"],
        alternatives=state.get("alternatives") or [],
        weather=state.get("weather"),
        weather_options=state.get("weather_options") or [],
        best_window_by_candidate=best_per_candidate,
        fuel_stops=state.get("fuel_stops") or [],
        gear=state.get("gear") or [],
        briefing=state.get("briefing") or "",
        warnings=state.get("warnings") or [],
    )
    return {"plan": plan, "progress": ["Plan ready"]}
