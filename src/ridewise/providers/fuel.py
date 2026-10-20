"""Fuel stations from OpenStreetMap via Overpass, turned into a refuelling plan."""

from __future__ import annotations

import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ridewise.config import get_settings
from ridewise.geo import Point, cumulative_km, haversine_km, sample_along
from ridewise.models import FuelStop, Motorcycle

logger = logging.getLogger(__name__)

# Overpass charges for every coordinate in an `around` clause, so the route is
# thinned to this many probe points before asking.
MAX_PROBE_POINTS = 40
SEARCH_RADIUS_M = 3000


class FuelError(RuntimeError):
    """Overpass refused or returned something unusable."""


def _overpass_query(points: list[Point], radius_m: int) -> str:
    coords = ",".join(f"{lat:.4f},{lon:.4f}" for lat, lon in points)
    return (
        "[out:json][timeout:50];"
        f'(node(around:{radius_m},{coords})["amenity"="fuel"];'
        f'way(around:{radius_m},{coords})["amenity"="fuel"];);'
        "out center tags;"
    )


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, max=20),
    reraise=True,
)
def _ask_overpass(query: str, client: httpx.Client, url: str) -> dict:
    response = client.post(url, data={"data": query})
    response.raise_for_status()
    return response.json()


def find_fuel_stations(
    geometry: list[Point],
    *,
    radius_m: int = SEARCH_RADIUS_M,
    client: httpx.Client | None = None,
) -> list[FuelStop]:
    """Every fuel station within `radius_m` of the route, ordered along it."""
    if len(geometry) < 2:
        return []

    settings = get_settings()
    probes = [point for _, point in sample_along(geometry, min(MAX_PROBE_POINTS, len(geometry)))]
    owns_client = client is None
    client = client or httpx.Client(timeout=settings.http_timeout)

    try:
        payload = _ask_overpass(_overpass_query(probes, radius_m), client, settings.overpass_url)
    except httpx.HTTPError as exc:
        raise FuelError(f"Overpass request failed: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    marks = cumulative_km(geometry)
    stops: list[FuelStop] = []
    for element in payload.get("elements", []):
        centre = element.get("center") or element
        lat, lon = centre.get("lat"), centre.get("lon")
        if lat is None or lon is None:
            continue
        tags = element.get("tags", {})

        # Attach the station to its nearest point on the route.
        nearest_idx, nearest_km = min(
            ((i, haversine_km((lat, lon), p)) for i, p in enumerate(geometry)),
            key=lambda pair: pair[1],
        )
        stops.append(
            FuelStop(
                name=tags.get("name") or tags.get("brand") or "Unnamed fuel station",
                brand=tags.get("brand", ""),
                lat=float(lat),
                lon=float(lon),
                distance_along_km=marks[nearest_idx],
                detour_km=nearest_km,
            )
        )

    stops.sort(key=lambda s: s.distance_along_km)
    return stops


def plan_fuel_stops(
    geometry: list[Point],
    bike: Motorcycle,
    *,
    stations: list[FuelStop] | None = None,
    safety_margin: float = 0.85,
    client: httpx.Client | None = None,
) -> tuple[list[FuelStop], list[str]]:
    """Pick the stations this bike actually needs, and flag what it cannot reach.

    Range is the usable tank (tank minus reserve) times `safety_margin`, so the
    plan does not assume the rider rides into the reserve light.
    """
    warnings: list[str] = []
    if len(geometry) < 2:
        return [], warnings

    total_km = cumulative_km(geometry)[-1]
    usable_range = bike.range_km * safety_margin

    if usable_range <= 0:
        warnings.append(
            f"{bike.label} has no usable range configured - check its tank and consumption."
        )
        return [], warnings
    if total_km <= usable_range:
        return [], warnings

    if stations is None:
        try:
            stations = find_fuel_stations(geometry, client=client)
        except FuelError as exc:
            warnings.append(f"Could not look up fuel stations: {exc}")
            return [], warnings

    if not stations:
        warnings.append(
            f"This {total_km:.0f} km route exceeds the {usable_range:.0f} km range of "
            f"{bike.label}, and OpenStreetMap lists no fuel stations near it. Carry fuel."
        )
        return [], warnings

    chosen: list[FuelStop] = []
    tank_empty_at = usable_range

    while tank_empty_at < total_km:
        # The last station the bike can still reach on the current tank. A small
        # lead-in stops it picking a station metres from the start.
        reachable = [
            s
            for s in stations
            if s.distance_along_km <= tank_empty_at
            and s.distance_along_km > (chosen[-1].distance_along_km if chosen else 0) + 10
        ]
        if not reachable:
            warnings.append(
                f"No fuel station found between km "
                f"{(chosen[-1].distance_along_km if chosen else 0):.0f} and "
                f"km {tank_empty_at:.0f}; {bike.label} cannot cover that stretch on one tank."
            )
            break

        stop = max(reachable, key=lambda s: s.distance_along_km)
        remaining = total_km - stop.distance_along_km
        stop.reason = (
            f"km {stop.distance_along_km:.0f} - last station within the "
            f"{usable_range:.0f} km range; {remaining:.0f} km still to ride"
        )
        chosen.append(stop)
        tank_empty_at = stop.distance_along_km + usable_range

    return chosen, warnings
