"""Builders for synthetic rides, so tests need no network."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from ridewise.geo import destination_point
from ridewise.models import (
    BikeCategory,
    GeoPlace,
    HourlyWeather,
    Motorcycle,
    RideRequest,
    RiderProfile,
    RouteCandidate,
    TireType,
    WindProtection,
)
from ridewise.providers.weather import PointForecast

LVIV = (49.8397, 24.0297)


def ring_geometry(
    centre: tuple[float, float] = LVIV, radius_km: float = 39.8, points: int = 180
) -> list[tuple[float, float]]:
    """A closed circle; circumference is 2*pi*radius, so ~250 km at 39.8 km."""
    ring = [destination_point(centre, 360 * i / points, radius_km) for i in range(points)]
    ring.append(ring[0])
    return ring


def route(
    *,
    distance_km: float = 250.0,
    duration_h: float = 5.0,
    geometry: list[tuple[float, float]] | None = None,
    twistiness: float = 30.0,
    ascent_m: float = 1200.0,
    candidate_id: str = "c1",
    bearing_deg: float = 45.0,
) -> RouteCandidate:
    return RouteCandidate(
        candidate_id=candidate_id,
        bearing_deg=bearing_deg,
        distance_km=distance_km,
        moving_duration_h=duration_h,
        ascent_m=ascent_m,
        descent_m=ascent_m,
        twistiness=twistiness,
        geometry=geometry if geometry is not None else ring_geometry(),
    )


def request(
    *,
    target_distance_km: float = 250.0,
    ride_date: date | None = None,
    earliest: time = time(8, 0),
    latest: time = time(19, 0),
    prefer_twisty: bool = True,
) -> RideRequest:
    return RideRequest(
        start=GeoPlace(label="Lviv, Ukraine", lat=LVIV[0], lon=LVIV[1]),
        target_distance_km=target_distance_km,
        ride_date=ride_date or date(2026, 6, 20),
        earliest_departure=earliest,
        latest_return=latest,
        prefer_twisty=prefer_twisty,
    )


def profile(*, min_temp: float = 8.0, accepts_rain: bool = False) -> RiderProfile:
    return RiderProfile(
        name="Test Rider",
        home_label="Lviv, Ukraine",
        min_comfortable_temp_c=min_temp,
        accepts_rain=accepts_rain,
    )


def bike(*, tank: float = 16.0, consumption: float = 4.3, reserve: float = 2.5) -> Motorcycle:
    return Motorcycle(
        nickname="Test",
        make="Yamaha",
        model="Tenere 700",
        year=2023,
        category=BikeCategory.ADVENTURE,
        tank_liters=tank,
        consumption_l_per_100km=consumption,
        reserve_liters=reserve,
        wind_protection=WindProtection.LOW,
        tire_type=TireType.DUAL_SPORT,
    )


def hour(
    when: datetime,
    *,
    temp: float = 18.0,
    rain_pct: float = 0.0,
    rain_mm: float = 0.0,
    gusts: float = 15.0,
    code: int = 1,
) -> HourlyWeather:
    return HourlyWeather(
        time=when,
        temperature_c=temp,
        apparent_temperature_c=temp,
        precipitation_mm=rain_mm,
        precipitation_probability=rain_pct,
        wind_speed_kmh=gusts * 0.6,
        wind_gusts_kmh=gusts,
        cloud_cover=30.0,
        visibility_m=20000.0,
        weather_code=code,
    )


def forecast(
    day: date,
    *,
    lat: float = LVIV[0],
    lon: float = LVIV[1],
    hours: int = 48,
    rain_from_hour: int | None = None,
) -> PointForecast:
    """A flat day, optionally turning wet from a given hour onwards."""
    start = datetime.combine(day, time(0, 0))
    series = []
    for i in range(hours):
        when = start + timedelta(hours=i)
        wet = rain_from_hour is not None and i >= rain_from_hour
        series.append(
            hour(
                when,
                temp=12.0 if wet else 20.0,
                rain_pct=95.0 if wet else 0.0,
                rain_mm=3.0 if wet else 0.0,
                gusts=50.0 if wet else 12.0,
                code=65 if wet else 1,
            )
        )
    return PointForecast(lat=lat, lon=lon, hours=series, utc_offset_s=10800)
