"""The state that flows through the planner graph."""

from __future__ import annotations

import operator
from datetime import date
from typing import Annotated, TypedDict

from ridewise.models import (
    FuelStop,
    GearItem,
    Motorcycle,
    RidePlan,
    RideRequest,
    RiderProfile,
    RouteCandidate,
    WeatherWindow,
)


class PlannerState(TypedDict, total=False):
    """One ride planning run.

    `warnings` and `progress` are reducer fields: nodes append to them rather
    than replacing them, so nothing a node noticed gets lost downstream.
    """

    # --- inputs ---
    raw_request: str
    today: date
    bike: Motorcycle
    profile: RiderProfile
    # Structured fallbacks from the UI form, used when there is no free text or
    # when the model cannot be reached.
    form_start_place: str
    form_distance_km: float
    form_ride_date: date
    form_earliest: str
    form_latest: str
    form_avoid_highways: bool
    form_prefer_twisty: bool

    # --- derived ---
    request: RideRequest
    candidates: list[RouteCandidate]
    # Departure options per candidate, keyed by candidate_id, so the choosing
    # node can weigh roads against weather for every option.
    candidate_windows: dict[str, list[WeatherWindow]]
    route: RouteCandidate
    alternatives: list[RouteCandidate]
    weather_options: list[WeatherWindow]
    weather: WeatherWindow | None
    fuel_stops: list[FuelStop]
    gear: list[GearItem]
    briefing: str
    plan: RidePlan

    # --- accumulated ---
    warnings: Annotated[list[str], operator.add]
    progress: Annotated[list[str], operator.add]
