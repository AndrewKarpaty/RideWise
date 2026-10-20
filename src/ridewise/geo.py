"""Geodesy helpers: everything RideWise needs to reason about shapes on a sphere.

Pure stdlib maths, no I/O - which makes this the easiest module to unit-test and
the one the route generator leans on hardest.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

EARTH_RADIUS_KM = 6371.0088

# A point is always (latitude, longitude) in degrees. GeoJSON uses the opposite
# order, so conversions live in the routing provider, never here.
Point = tuple[float, float]


def haversine_km(a: Point, b: Point) -> float:
    """Great-circle distance between two points."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, h)))


def destination_point(origin: Point, bearing_deg: float, distance_km: float) -> Point:
    """The point reached by travelling `distance_km` from `origin` on `bearing_deg`."""
    lat1, lon1 = math.radians(origin[0]), math.radians(origin[1])
    theta = math.radians(bearing_deg)
    delta = distance_km / EARTH_RADIUS_KM

    lat2 = math.asin(
        math.sin(lat1) * math.cos(delta) + math.cos(lat1) * math.sin(delta) * math.cos(theta)
    )
    lon2 = lon1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(lat1),
        math.cos(delta) - math.sin(lat1) * math.sin(lat2),
    )
    return (math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180)


def initial_bearing(a: Point, b: Point) -> float:
    """Compass bearing in degrees (0-360) when leaving `a` towards `b`."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def bearing_delta(from_deg: float, to_deg: float) -> float:
    """Signed smallest turn from one bearing to another, in [-180, 180).

    An exact reversal comes back as -180: the sign of a half-turn is arbitrary,
    and every caller takes the absolute value.
    """
    return (to_deg - from_deg + 540) % 360 - 180


def path_length_km(points: Sequence[Point]) -> float:
    return sum(haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1))


def cumulative_km(points: Sequence[Point]) -> list[float]:
    """Distance travelled along the path at each vertex; starts at 0.0."""
    out = [0.0]
    for i in range(len(points) - 1):
        out.append(out[-1] + haversine_km(points[i], points[i + 1]))
    return out


def point_at_km(points: Sequence[Point], target_km: float) -> Point:
    """Interpolate the position reached after `target_km` along the path."""
    if not points:
        raise ValueError("cannot interpolate an empty path")
    marks = cumulative_km(points)
    if target_km <= 0:
        return points[0]
    if target_km >= marks[-1]:
        return points[-1]

    for i in range(len(marks) - 1):
        if marks[i + 1] >= target_km:
            span = marks[i + 1] - marks[i]
            frac = 0.0 if span == 0 else (target_km - marks[i]) / span
            lat = points[i][0] + (points[i + 1][0] - points[i][0]) * frac
            lon = points[i][1] + (points[i + 1][1] - points[i][1]) * frac
            return (lat, lon)
    return points[-1]


def sample_along(points: Sequence[Point], count: int) -> list[tuple[float, Point]]:
    """`count` evenly-spaced samples as (distance_km, point), ends included."""
    if count < 2:
        raise ValueError("need at least two samples")
    total = path_length_km(points)
    step = total / (count - 1)
    return [(step * i, point_at_km(points, step * i)) for i in range(count)]


def _thin(points: Sequence[Point], min_segment_km: float) -> list[Point]:
    """Drop vertices closer together than `min_segment_km`.

    Routing geometry comes back with metre-scale vertices; measuring heading
    change across those measures GPS noise, not corners.
    """
    if len(points) < 3:
        return list(points)
    kept = [points[0]]
    for p in points[1:-1]:
        if haversine_km(kept[-1], p) >= min_segment_km:
            kept.append(p)
    kept.append(points[-1])
    return kept


def twistiness(points: Sequence[Point], min_segment_km: float = 0.2) -> float:
    """Mean absolute heading change in degrees per kilometre.

    A motorway sits near 0; a mountain pass with switchbacks runs 60+. This is
    the number that separates "250 km of dual carriageway" from "a good ride".
    """
    thinned = _thin(points, min_segment_km)
    if len(thinned) < 3:
        return 0.0
    total_km = path_length_km(thinned)
    if total_km <= 0:
        return 0.0

    turning = 0.0
    previous = initial_bearing(thinned[0], thinned[1])
    for i in range(1, len(thinned) - 1):
        current = initial_bearing(thinned[i], thinned[i + 1])
        turning += abs(bearing_delta(previous, current))
        previous = current
    return turning / total_km


def bbox(points: Sequence[Point]) -> tuple[float, float, float, float]:
    """(min_lat, min_lon, max_lat, max_lon) - what folium needs to fit bounds."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return (min(lats), min(lons), max(lats), max(lons))


def loop_waypoints(start: Point, radius_km: float, bearing_deg: float, count: int) -> list[Point]:
    """Waypoints for a loop that leaves `start`, heads out on `bearing_deg`, and returns.

    The waypoints sit on a circle of radius `radius_km` whose centre is that same
    distance away on `bearing_deg` - so `start` lies on the circle too, and the
    loop reaches roughly `2 * radius_km` out at its far side.
    """
    if count < 2:
        raise ValueError("a loop needs at least two intermediate waypoints")
    centre = destination_point(start, bearing_deg, radius_km)
    start_bearing_from_centre = (bearing_deg + 180) % 360
    step = 360 / (count + 1)
    return [
        destination_point(centre, start_bearing_from_centre + step * (i + 1), radius_km)
        for i in range(count)
    ]


def radius_for_target_distance(target_km: float, waypoints: int, winding: float = 1.25) -> float:
    """First guess at the loop radius that yields `target_km` of road.

    The inscribed polygon through `waypoints + 1` vertices has perimeter
    `2 * n * R * sin(pi / n)`; real roads wander, hence the `winding` factor.
    The route generator refines this against what the router actually returns.
    """
    n = waypoints + 1
    perimeter_per_radius = 2 * n * math.sin(math.pi / n)
    return target_km / (perimeter_per_radius * winding)
