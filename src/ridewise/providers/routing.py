"""OpenRouteService client: geocoding plus the loop-route generator.

ORS can generate round trips itself, but the public plan caps them at 100 km -
too short for a real day ride. So RideWise builds the loop geometrically (a ring
of waypoints around the start) and asks ORS for ordinary directions through it,
which is capped at 6000 km / 50 waypoints instead. The upside: we choose the
shape, so we can generate several candidates in different directions and score
them on how twisty the roads turned out.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ridewise.config import get_settings
from ridewise.geo import (
    Point,
    loop_waypoints,
    radius_for_target_distance,
    twistiness,
)
from ridewise.models import GeoPlace, RouteCandidate

logger = logging.getLogger(__name__)

# Keeps a loop on back roads. `highways` and `tollways` are driving-* only,
# which is exactly the profile we use.
TWISTY_AVOID = ["highways", "tollways", "ferries"]
FAST_AVOID = ["ferries"]


class RoutingError(RuntimeError):
    """ORS refused the request or could not route it."""


@dataclass(slots=True)
class Route:
    """A routed path, straight from ORS."""

    geometry: list[Point]
    distance_km: float
    duration_h: float
    ascent_m: float
    descent_m: float


class RoutingClient:
    def __init__(self, client: httpx.Client | None = None):
        self.settings = get_settings()
        if not self.settings.ors_api_key:
            raise RoutingError(
                "RIDEWISE_ORS_API_KEY is not set - get a free key at "
                "https://openrouteservice.org/dev/#/signup"
            )
        self._client = client or httpx.Client(timeout=self.settings.http_timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> RoutingClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- plumbing ---------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    def _post(self, path: str, body: dict) -> dict:
        response = self._client.post(
            f"{self.settings.ors_base_url}{path}",
            json=body,
            headers={
                "Authorization": self.settings.ors_api_key or "",
                "Content-Type": "application/json",
                "Accept": "application/geo+json",
            },
        )
        if response.status_code >= 400:
            raise RoutingError(self._explain(response))
        return response.json()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    def _get(self, path: str, params: dict) -> dict:
        response = self._client.get(
            f"{self.settings.ors_base_url}{path}",
            params={**params, "api_key": self.settings.ors_api_key},
        )
        if response.status_code >= 400:
            raise RoutingError(self._explain(response))
        return response.json()

    @staticmethod
    def _explain(response: httpx.Response) -> str:
        """ORS puts a useful code and message in the body; surface it."""
        try:
            error = response.json().get("error", {})
        except ValueError:
            return f"ORS HTTP {response.status_code}: {response.text[:200]}"
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message", "")
            return f"ORS HTTP {response.status_code} (code {code}): {message}"
        return f"ORS HTTP {response.status_code}: {error}"

    # -- geocoding --------------------------------------------------------

    def geocode(self, text: str, limit: int = 5) -> list[GeoPlace]:
        payload = self._get("/geocode/search", {"text": text, "size": limit})
        places: list[GeoPlace] = []
        for feature in payload.get("features", []):
            lon, lat = feature["geometry"]["coordinates"][:2]
            label = feature.get("properties", {}).get("label") or text
            places.append(GeoPlace(label=label, lat=lat, lon=lon))
        return places

    def geocode_one(self, text: str) -> GeoPlace:
        places = self.geocode(text, limit=1)
        if not places:
            raise RoutingError(f"could not find a place called {text!r}")
        return places[0]

    def reverse_geocode(self, point: Point) -> str:
        payload = self._get(
            "/geocode/reverse", {"point.lat": point[0], "point.lon": point[1], "size": 1}
        )
        features = payload.get("features", [])
        if not features:
            return f"{point[0]:.4f}, {point[1]:.4f}"
        return features[0].get("properties", {}).get("label", "")

    # -- directions -------------------------------------------------------

    def directions(
        self,
        coordinates: list[Point],
        *,
        avoid_features: list[str] | None = None,
        profile: str | None = None,
    ) -> Route:
        """Route through `coordinates` in order, with elevation."""
        if len(coordinates) < 2:
            raise RoutingError("a route needs at least two coordinates")
        if len(coordinates) > 50:
            raise RoutingError(f"ORS allows 50 waypoints, got {len(coordinates)}")

        profile = profile or self.settings.ors_profile
        body: dict = {
            # ORS speaks [lon, lat].
            "coordinates": [[lon, lat] for lat, lon in coordinates],
            "elevation": True,
            "instructions": False,
            # -1 lets ORS snap a waypoint to the nearest road at any distance,
            # which stops a generated waypoint landing in a lake from failing
            # the whole route.
            "radiuses": [-1] * len(coordinates),
        }
        if avoid_features:
            body["options"] = {"avoid_features": avoid_features}

        payload = self._post(f"/v2/directions/{profile}/geojson", body)
        features = payload.get("features") or []
        if not features:
            raise RoutingError("ORS returned no route")

        feature = features[0]
        properties = feature.get("properties", {})
        summary = properties.get("summary", {})
        coords = feature.get("geometry", {}).get("coordinates", [])
        # Elevation adds a third ordinate; keep lat/lon only.
        geometry = [(c[1], c[0]) for c in coords]
        if not geometry:
            raise RoutingError("ORS returned an empty geometry")

        return Route(
            geometry=geometry,
            distance_km=float(summary.get("distance", 0.0)) / 1000,
            duration_h=float(summary.get("duration", 0.0)) / 3600,
            ascent_m=float(properties.get("ascent", 0.0)),
            descent_m=float(properties.get("descent", 0.0)),
        )

    # -- loop generation --------------------------------------------------

    def fit_loop(
        self,
        start: Point,
        target_km: float,
        bearing_deg: float,
        *,
        candidate_id: str,
        avoid_features: list[str] | None = None,
        waypoint_count: int | None = None,
    ) -> RouteCandidate:
        """A loop from `start` heading out on `bearing_deg`, close to `target_km`.

        The first radius is a geometric estimate; each attempt rescales it by how
        far off the routed distance came back, which converges in two or three
        calls because road distance is close to linear in the ring radius.
        """
        settings = self.settings
        waypoint_count = waypoint_count or settings.waypoints_per_loop
        radius = radius_for_target_distance(target_km, waypoint_count)

        best: tuple[float, Route, list[Point]] | None = None
        last_error: Exception | None = None

        for attempt in range(settings.route_fit_attempts):
            waypoints = loop_waypoints(start, radius, bearing_deg, waypoint_count)
            try:
                route = self.directions([start, *waypoints, start], avoid_features=avoid_features)
            except RoutingError as exc:
                # A ring that cannot be routed is usually one bad waypoint;
                # shrink a little and try again rather than losing the candidate.
                last_error = exc
                logger.warning(
                    "loop attempt %d on bearing %.0f failed: %s", attempt + 1, bearing_deg, exc
                )
                radius *= 0.85
                continue

            error = abs(route.distance_km - target_km) / target_km
            if best is None or error < best[0]:
                best = (error, route, waypoints)
            if error <= settings.route_fit_tolerance:
                break
            if route.distance_km <= 0:
                break
            # Rescale towards the target, clamped so one odd result cannot send
            # the next attempt somewhere absurd.
            scale = min(max(target_km / route.distance_km, 0.5), 2.0)
            radius *= scale

        if best is None:
            raise RoutingError(f"could not build a loop on bearing {bearing_deg:.0f}: {last_error}")

        _, route, waypoints = best
        return RouteCandidate(
            candidate_id=candidate_id,
            bearing_deg=bearing_deg,
            distance_km=route.distance_km,
            moving_duration_h=route.duration_h,
            ascent_m=route.ascent_m,
            descent_m=route.descent_m,
            twistiness=twistiness(route.geometry),
            geometry=route.geometry,
            waypoints=waypoints,
        )
