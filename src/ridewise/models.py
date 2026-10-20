"""Domain model: the garage (persisted) and the ride plan (produced per request)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import StrEnum

from pydantic import BaseModel, computed_field
from pydantic import Field as PydanticField
from sqlmodel import Field, SQLModel

# ---------------------------------------------------------------------------
# Garage - persisted in SQLite
# ---------------------------------------------------------------------------


class BikeCategory(StrEnum):
    SPORT = "sport"
    NAKED = "naked"
    ADVENTURE = "adventure"
    TOURING = "touring"
    CRUISER = "cruiser"
    SUPERMOTO = "supermoto"
    ENDURO = "enduro"
    SCOOTER = "scooter"


class WindProtection(StrEnum):
    NONE = "none"
    LOW = "low"
    FULL = "full"


class TireType(StrEnum):
    SPORT = "sport"
    ROAD = "road"
    TOURING = "touring"
    DUAL_SPORT = "dual-sport"
    KNOBBY = "knobby"


class Experience(StrEnum):
    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    EXPERIENCED = "experienced"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Motorcycle(SQLModel, table=True):
    """One bike in the rider's garage.

    The fuel figures are what turn a route into a refuelling plan, and the
    protection/tyre figures are what turn a forecast into a gear list - so they
    are required rather than optional.
    """

    id: int | None = Field(default=None, primary_key=True)
    nickname: str = Field(index=True)
    make: str
    model: str
    year: int | None = None
    category: BikeCategory = BikeCategory.NAKED

    tank_liters: float
    consumption_l_per_100km: float
    reserve_liters: float = 2.0

    wind_protection: WindProtection = WindProtection.LOW
    tire_type: TireType = TireType.ROAD
    heated_grips: bool = False
    has_luggage: bool = False

    notes: str = ""
    photo_path: str | None = None
    is_default: bool = False
    created_at: datetime = Field(default_factory=_utcnow)

    @property
    def label(self) -> str:
        base = f"{self.make} {self.model}".strip()
        return f"{base} ({self.year})" if self.year else base

    @property
    def usable_liters(self) -> float:
        return max(self.tank_liters - self.reserve_liters, 0.0)

    @property
    def range_km(self) -> float:
        """Distance on the usable tank - i.e. before dipping into reserve."""
        if self.consumption_l_per_100km <= 0:
            return 0.0
        return self.usable_liters / self.consumption_l_per_100km * 100

    @property
    def full_tank_range_km(self) -> float:
        if self.consumption_l_per_100km <= 0:
            return 0.0
        return self.tank_liters / self.consumption_l_per_100km * 100


class RiderProfile(SQLModel, table=True):
    """The rider's cabinet. One row for now; `id` is here for when that changes."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = "Rider"
    home_label: str = ""
    home_lat: float | None = None
    home_lon: float | None = None
    experience: Experience = Experience.INTERMEDIATE
    min_comfortable_temp_c: float = 8.0
    accepts_rain: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class SavedPlan(SQLModel, table=True):
    """A ride plan kept for history, stored as the JSON of `RidePlan`."""

    id: int | None = Field(default=None, primary_key=True)
    title: str
    ride_date: date
    distance_km: float
    motorcycle_id: int | None = Field(default=None, foreign_key="motorcycle.id")
    payload: str  # RidePlan.model_dump_json()
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Planning - produced per request, flows through the LangGraph state
# ---------------------------------------------------------------------------

_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class GeoPlace(BaseModel):
    label: str
    lat: float
    lon: float

    @property
    def point(self) -> tuple[float, float]:
        return (self.lat, self.lon)


class RideRequest(BaseModel):
    """A ride intent, normalised out of whatever the rider typed."""

    raw_text: str = ""
    start: GeoPlace
    target_distance_km: float = PydanticField(ge=20, le=1200)
    ride_date: date
    earliest_departure: time = time(8, 0)
    latest_return: time = time(19, 0)
    avoid_highways: bool = True
    prefer_twisty: bool = True
    notes: str = ""


class RouteCandidate(BaseModel):
    candidate_id: str
    bearing_deg: float
    distance_km: float
    moving_duration_h: float
    ascent_m: float = 0.0
    descent_m: float = 0.0
    twistiness: float = 0.0
    geometry: list[tuple[float, float]] = PydanticField(default_factory=list, repr=False)
    waypoints: list[tuple[float, float]] = PydanticField(default_factory=list)
    road_score: float = 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def direction(self) -> str:
        idx = int((self.bearing_deg % 360) / 45 + 0.5) % 8
        return _COMPASS[idx]

    @property
    def name(self) -> str:
        return f"{self.distance_km:.0f} km {self.direction} loop"


class HourlyWeather(BaseModel):
    time: datetime
    temperature_c: float
    apparent_temperature_c: float
    precipitation_mm: float
    precipitation_probability: float
    wind_speed_kmh: float
    wind_gusts_kmh: float
    cloud_cover: float
    visibility_m: float | None = None
    weather_code: int = 0


class LegForecast(BaseModel):
    """Weather where the rider will be, at the time they will be there."""

    distance_along_km: float
    lat: float
    lon: float
    eta: datetime
    weather: HourlyWeather


class WeatherWindow(BaseModel):
    departure: datetime
    arrival: datetime
    score: float  # 0-100 rideability
    rain_risk_pct: float
    min_temp_c: float
    max_temp_c: float
    max_gust_kmh: float
    total_precipitation_mm: float
    verdict: str = ""
    legs: list[LegForecast] = PydanticField(default_factory=list)

    @property
    def duration_h(self) -> float:
        return (self.arrival - self.departure).total_seconds() / 3600


class FuelStop(BaseModel):
    name: str
    brand: str = ""
    lat: float
    lon: float
    distance_along_km: float
    detour_km: float = 0.0
    reason: str = ""


class GearItem(BaseModel):
    item: str
    reason: str
    essential: bool = True


class RidePlan(BaseModel):
    request: RideRequest
    bike_label: str
    route: RouteCandidate
    alternatives: list[RouteCandidate] = PydanticField(default_factory=list)
    weather: WeatherWindow | None = None
    weather_options: list[WeatherWindow] = PydanticField(default_factory=list)
    # Each candidate's own best window, keyed by `candidate_id`, so a UI can
    # show every option with the departure and score it would actually get
    # rather than only the winner's.
    best_window_by_candidate: dict[str, WeatherWindow] = PydanticField(default_factory=dict)
    fuel_stops: list[FuelStop] = PydanticField(default_factory=list)
    gear: list[GearItem] = PydanticField(default_factory=list)
    briefing: str = ""
    warnings: list[str] = PydanticField(default_factory=list)
