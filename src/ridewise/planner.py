"""Scoring and selection - the deterministic half of the planner.

Nothing here calls an LLM. Route quality, the weather window and the fuel maths
are arithmetic, and keeping them out of the model makes them testable and cheap.
The LLM's job is the briefing and the gear list, where judgement actually helps.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from ridewise.geo import sample_along
from ridewise.models import (
    HourlyWeather,
    LegForecast,
    RideRequest,
    RiderProfile,
    RouteCandidate,
    WeatherWindow,
)
from ridewise.providers.weather import WET_CODES, PointForecast, describe_code

# Riding a loop takes longer than the router's moving time: fuel, photos, coffee.
ELAPSED_FACTOR = 1.25


# ---------------------------------------------------------------------------
# Route quality
# ---------------------------------------------------------------------------

# Above this many degrees of turning per km, a road is as twisty as it needs to
# be; scoring past it would just reward hairpin noise.
TWISTINESS_CAP = 55.0
ASCENT_CAP_M = 2500.0


def score_route(candidate: RouteCandidate, request: RideRequest) -> float:
    """0-100 on how good the roads are, before weather is considered."""
    accuracy = 1 - min(
        abs(candidate.distance_km - request.target_distance_km) / request.target_distance_km, 1.0
    )
    twist = min(candidate.twistiness / TWISTINESS_CAP, 1.0)
    climb = min(candidate.ascent_m / ASCENT_CAP_M, 1.0)

    if request.prefer_twisty:
        return 100 * (0.30 * accuracy + 0.50 * twist + 0.20 * climb)
    return 100 * (0.55 * accuracy + 0.20 * twist + 0.25 * climb)


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------


def rideability(hour: HourlyWeather, profile: RiderProfile) -> tuple[float, list[str]]:
    """0-100 for one hour at one place, plus the reasons points were lost."""
    score = 100.0
    reasons: list[str] = []

    if hour.precipitation_probability > 0:
        penalty = 0.55 * hour.precipitation_probability
        if not profile.accepts_rain:
            penalty *= 1.25
        score -= penalty
        if hour.precipitation_probability >= 40:
            reasons.append(f"{hour.precipitation_probability:.0f}% chance of rain")

    if hour.precipitation_mm > 0:
        score -= min(10 * hour.precipitation_mm, 35)
        if hour.precipitation_mm >= 1.0:
            reasons.append(f"{hour.precipitation_mm:.1f} mm of rain")

    cold_gap = profile.min_comfortable_temp_c - hour.apparent_temperature_c
    if cold_gap > 0:
        score -= min(4.5 * cold_gap, 40)
        reasons.append(f"feels like {hour.apparent_temperature_c:.0f}C")
    if hour.apparent_temperature_c > 32:
        score -= min(2.5 * (hour.apparent_temperature_c - 32), 25)
        reasons.append(f"heat, feels like {hour.apparent_temperature_c:.0f}C")

    if hour.wind_gusts_kmh > 40:
        score -= min(1.1 * (hour.wind_gusts_kmh - 40), 30)
        reasons.append(f"gusts to {hour.wind_gusts_kmh:.0f} km/h")

    if hour.visibility_m is not None and hour.visibility_m < 2000:
        score -= 18
        reasons.append(f"visibility {hour.visibility_m / 1000:.1f} km")

    if hour.weather_code in {56, 57, 66, 67, 71, 73, 75, 77, 85, 86}:
        score -= 35
        reasons.append(f"{describe_code(hour.weather_code)} - risk of ice")
    elif hour.weather_code in {95, 96, 99}:
        score -= 30
        reasons.append("thunderstorms")

    return max(score, 0.0), reasons


def _verdict(score: float) -> str:
    if score >= 85:
        return "Excellent riding weather"
    if score >= 70:
        return "Good - ride it"
    if score >= 55:
        return "Rideable with the right gear"
    if score >= 35:
        return "Marginal - consider postponing"
    return "Poor - not a day for two wheels"


def elapsed_hours(candidate: RouteCandidate) -> float:
    return candidate.moving_duration_h * ELAPSED_FACTOR


def build_window(
    candidate: RouteCandidate,
    forecasts: list[PointForecast],
    departure: datetime,
    profile: RiderProfile,
) -> WeatherWindow | None:
    """Score one departure time by the weather at each point when the rider gets there.

    This is the part a plain "forecast for the day" misses: leaving at 09:00
    versus 13:00 can put you at the far side of the loop either side of a front.
    """
    duration = elapsed_hours(candidate)
    arrival = departure + timedelta(hours=duration)
    samples = sample_along(candidate.geometry, len(forecasts))

    legs: list[LegForecast] = []
    scores: list[float] = []
    reasons: list[str] = []

    for (distance_km, point), forecast in zip(samples, forecasts, strict=True):
        fraction = distance_km / candidate.distance_km if candidate.distance_km else 0.0
        eta = departure + timedelta(hours=duration * fraction)
        hour = forecast.at(eta)
        if hour is None:
            return None  # forecast does not cover this hour

        score, why = rideability(hour, profile)
        scores.append(score)
        reasons.extend(why)
        legs.append(
            LegForecast(
                distance_along_km=distance_km,
                lat=point[0],
                lon=point[1],
                eta=eta,
                weather=hour,
            )
        )

    if not scores:
        return None

    # The worst stretch matters more than the average - an hour of hail ruins a
    # ride that is otherwise sunny - so the minimum carries real weight.
    mean = sum(scores) / len(scores)
    overall = 0.6 * mean + 0.4 * min(scores)

    temps = [leg.weather.apparent_temperature_c for leg in legs]
    hours = [leg.weather for leg in legs]
    headline = max(
        (h for h in hours), key=lambda h: (h.weather_code in WET_CODES, h.precipitation_probability)
    )

    unique_reasons = list(dict.fromkeys(reasons))[:3]
    verdict = _verdict(overall)
    if unique_reasons:
        verdict = f"{verdict} - {', '.join(unique_reasons)}"
    else:
        verdict = f"{verdict} - {describe_code(headline.weather_code)}"

    return WeatherWindow(
        departure=departure,
        arrival=arrival,
        score=round(overall, 1),
        rain_risk_pct=round(max(h.precipitation_probability for h in hours), 0),
        min_temp_c=round(min(temps), 1),
        max_temp_c=round(max(temps), 1),
        max_gust_kmh=round(max(h.wind_gusts_kmh for h in hours), 0),
        total_precipitation_mm=round(sum(h.precipitation_mm for h in hours), 1),
        verdict=verdict,
        legs=legs,
    )


def candidate_departures(request: RideRequest, candidate: RouteCandidate) -> list[datetime]:
    """Every whole hour the ride both starts and finishes inside the rider's day."""
    duration = elapsed_hours(candidate)
    earliest = datetime.combine(request.ride_date, request.earliest_departure)
    latest_return = datetime.combine(request.ride_date, request.latest_return)

    # Start on the hour.
    first = earliest.replace(minute=0, second=0, microsecond=0)
    if first < earliest:
        first += timedelta(hours=1)

    out: list[datetime] = []
    cursor = first
    while cursor + timedelta(hours=duration) <= latest_return:
        out.append(cursor)
        cursor += timedelta(hours=1)

    # If the day is too short for the loop, still offer the earliest start so the
    # rider gets a plan plus a warning rather than nothing at all.
    return out or [first]


def best_windows(
    candidate: RouteCandidate,
    forecasts: list[PointForecast],
    request: RideRequest,
    profile: RiderProfile,
    limit: int = 4,
) -> list[WeatherWindow]:
    """Departure options for one route, best first."""
    windows = [
        window
        for departure in candidate_departures(request, candidate)
        if (window := build_window(candidate, forecasts, departure, profile)) is not None
    ]
    windows.sort(key=lambda w: w.score, reverse=True)
    return windows[:limit]


def combined_score(route_score: float, window: WeatherWindow | None) -> float:
    """How a candidate ranks once its best weather window is taken into account."""
    if window is None:
        return route_score * 0.5
    return 0.45 * route_score + 0.55 * window.score


def day_bounds(request: RideRequest) -> tuple[time, time]:
    return request.earliest_departure, request.latest_return
