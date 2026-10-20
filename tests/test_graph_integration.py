"""End-to-end run of the planner graph with every external call mocked.

This is the test that proves the wiring: intake -> routes -> weather -> choose
-> fuel -> gear -> briefing -> assemble, with ORS, Open-Meteo, Overpass and the
LLM all stubbed. It is the closest thing to a real plan that needs no API keys.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from itertools import pairwise

import httpx
import pytest
import respx

from ridewise.agent.graph import plan_ride, plan_ride_stream
from ridewise.agent.nodes import PlannerFailure
from ridewise.geo import destination_point, path_length_km
from ridewise.models import RidePlan
from tests import factories as f

RIDE_DATE = date.today() + timedelta(days=1)


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


def _ors_geometry(coordinates: list[list[float]]) -> list[list[float]]:
    """Densify the requested waypoint ring into a plausible routed geometry.

    Fifteen points per leg gives `twistiness` something real to measure instead
    of a handful of straight hops.
    """
    dense: list[list[float]] = []
    for (lon1, lat1), (lon2, lat2) in pairwise(coordinates):
        for step in range(15):
            t = step / 15
            dense.append([lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t])
    dense.append(coordinates[-1])
    return dense


def _directions_response(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    coordinates = body["coordinates"]
    geometry = _ors_geometry(coordinates)

    # Report a distance consistent with the ring the planner actually asked for,
    # inflated to mimic roads that wander, so fit_loop's refinement is exercised.
    straight_km = path_length_km([(lat, lon) for lon, lat in geometry])
    distance_m = straight_km * 1.25 * 1000

    return httpx.Response(
        200,
        json={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": geometry},
                    "properties": {
                        "summary": {
                            "distance": distance_m,
                            "duration": distance_m / 1000 / 55 * 3600,
                        },
                        "ascent": 980.0,
                        "descent": 980.0,
                    },
                }
            ],
        },
    )


def _geocode_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [f.LVIV[1], f.LVIV[0]]},
                    "properties": {"label": "Lviv, Lviv Oblast, Ukraine"},
                }
            ]
        },
    )


def _open_meteo_response(request: httpx.Request) -> httpx.Response:
    """A day that turns wet at 15:00, for every requested location."""
    lats = request.url.params["latitude"].split(",")
    lons = request.url.params["longitude"].split(",")

    start = datetime.combine(RIDE_DATE, time(0, 0))
    times, temps, apparent, precip, prob, wind, gusts, clouds, vis, codes = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
    for i in range(48):
        when = start + timedelta(hours=i)
        wet = 15 <= (i % 24) < 22
        times.append(when.isoformat(timespec="minutes"))
        temps.append(11.0 if wet else 19.0)
        apparent.append(9.0 if wet else 18.0)
        precip.append(2.5 if wet else 0.0)
        prob.append(90.0 if wet else 5.0)
        wind.append(30.0 if wet else 10.0)
        gusts.append(55.0 if wet else 18.0)
        clouds.append(100.0 if wet else 25.0)
        vis.append(4000.0 if wet else 24000.0)
        codes.append(65 if wet else 1)

    hourly = {
        "time": times,
        "temperature_2m": temps,
        "apparent_temperature": apparent,
        "precipitation": precip,
        "precipitation_probability": prob,
        "wind_speed_10m": wind,
        "wind_gusts_10m": gusts,
        "cloud_cover": clouds,
        "visibility": vis,
        "weather_code": codes,
    }

    blocks = [
        {
            "latitude": float(lat),
            "longitude": float(lon),
            "utc_offset_seconds": 10800,
            "timezone": "Europe/Kiev",
            "hourly": hourly,
        }
        for lat, lon in zip(lats, lons, strict=True)
    ]
    return httpx.Response(200, json=blocks if len(blocks) > 1 else blocks[0])


def _overpass_response(request: httpx.Request) -> httpx.Response:
    """Fuel stations scattered around the Lviv area."""
    elements = []
    for i in range(24):
        lat, lon = destination_point(f.LVIV, i * 15, 25 + (i % 5) * 8)
        elements.append(
            {
                "type": "node",
                "id": 1000 + i,
                "lat": lat,
                "lon": lon,
                "tags": {"amenity": "fuel", "name": f"OKKO {i}", "brand": "OKKO"},
            }
        )
    return httpx.Response(200, json={"elements": elements})


@pytest.fixture
def mocked_services():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__startswith="https://api.openrouteservice.org/geocode/search").mock(
            side_effect=_geocode_response
        )
        mock.post(url__regex=r"https://api\.openrouteservice\.org/v2/directions/.*").mock(
            side_effect=_directions_response
        )
        mock.get(url__startswith="https://api.open-meteo.com/v1/forecast").mock(
            side_effect=_open_meteo_response
        )
        mock.post(url__startswith="https://overpass-api.de/api/interpreter").mock(
            side_effect=_overpass_response
        )
        yield mock


@pytest.fixture
def fake_llm(monkeypatch):
    """Stub both LLM entry points as the nodes imported them."""

    def fake_chat_json(messages, schema, **kwargs):
        name = schema.__name__
        if name == "_Intake":
            return schema(
                start_place="Lviv",
                target_distance_km=250,
                ride_date=RIDE_DATE.isoformat(),
                earliest_departure="08:00",
                latest_return="19:00",
                avoid_highways=True,
                prefer_twisty=True,
                notes="wants a view for lunch",
            )
        if name == "_GearList":
            return schema(
                items=[
                    {"item": "Waterproof oversuit", "reason": "Rain from 15:00", "essential": True},
                    {
                        "item": "Thermal layer",
                        "reason": "Drops to 9C in the rain",
                        "essential": True,
                    },
                    {"item": "Clear visor", "reason": "Low light under cloud", "essential": False},
                ]
            )
        raise AssertionError(f"unexpected schema {name}")

    monkeypatch.setattr("ridewise.agent.nodes.chat_json", fake_chat_json)
    monkeypatch.setattr(
        "ridewise.agent.nodes.chat",
        lambda messages, **kwargs: "Leave at eight and you will beat the rain.",
    )


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_full_plan_is_produced(mocked_services, fake_llm):
    plan = plan_ride(
        raw_request="Twisty backroads tomorrow, about 250 km, back before dark",
        bike=f.bike(),
        profile=f.profile(),
        start_place="Lviv",
        distance_km=250,
        ride_date=RIDE_DATE,
        today=date.today(),
    )

    assert isinstance(plan, RidePlan)

    # Intake read the free text through the model.
    assert plan.request.start.label.startswith("Lviv")
    assert plan.request.notes == "wants a view for lunch"
    assert plan.request.ride_date == RIDE_DATE

    # A route was built, measured and scored.
    assert plan.route.geometry
    assert plan.route.distance_km > 0
    assert plan.route.twistiness > 0
    assert 0 <= plan.route.road_score <= 100
    assert plan.alternatives, "other candidate directions should be kept"

    # The weather window is ETA-aware and ordered.
    assert plan.weather is not None
    assert plan.weather.legs
    etas = [leg.eta for leg in plan.weather.legs]
    assert etas == sorted(etas)
    assert plan.weather.arrival > plan.weather.departure

    # The LLM stages landed.
    assert len(plan.gear) == 3
    assert any(item.essential for item in plan.gear)
    assert "beat the rain" in plan.briefing


def test_the_planner_avoids_the_wet_afternoon(mocked_services, fake_llm):
    """The fixture rains 15:00-22:00, so the chosen departure must be a morning one."""
    plan = plan_ride(
        bike=f.bike(),
        profile=f.profile(),
        start_place="Lviv",
        distance_km=250,
        ride_date=RIDE_DATE,
        earliest="06:00",
        latest="22:00",
        today=date.today(),
    )

    assert plan.weather is not None
    assert plan.weather.departure.hour <= 10, (
        f"chose {plan.weather.departure:%H:%M}, which rides into the rain"
    )
    # And the alternatives it rejected should score no better.
    assert all(w.score <= plan.weather.score for w in plan.weather_options)


def test_fuel_stops_are_planned_for_a_short_range_bike(mocked_services, fake_llm):
    thirsty = f.bike(tank=12, consumption=7.0, reserve=2.0)  # ~143 km usable

    plan = plan_ride(
        bike=thirsty,
        profile=f.profile(),
        start_place="Lviv",
        distance_km=250,
        ride_date=RIDE_DATE,
        today=date.today(),
    )

    assert plan.fuel_stops, "a 143 km range on a 250 km loop needs fuel"
    marks = [s.distance_along_km for s in plan.fuel_stops]
    assert marks == sorted(marks)
    assert all(s.reason for s in plan.fuel_stops)


def test_no_fuel_stop_for_a_long_range_bike(mocked_services, fake_llm):
    plan = plan_ride(
        bike=f.bike(tank=23, consumption=4.0, reserve=2.0),  # ~525 km usable
        profile=f.profile(),
        start_place="Lviv",
        distance_km=250,
        ride_date=RIDE_DATE,
        today=date.today(),
    )
    assert plan.fuel_stops == []


def test_progress_is_streamed_node_by_node(mocked_services, fake_llm):
    seen: list[str] = []
    for node, update in plan_ride_stream(
        bike=f.bike(),
        profile=f.profile(),
        start_place="Lviv",
        distance_km=250,
        ride_date=RIDE_DATE,
        today=date.today(),
    ):
        seen.append(node)
        assert isinstance(update, dict)

    assert seen == [
        "intake",
        "routes",
        "weather",
        "choose",
        "fuel",
        "gear",
        "briefing",
        "assemble",
    ]


def test_a_failing_llm_still_yields_a_plan(mocked_services, monkeypatch):
    """Route, weather and fuel must survive without the model."""
    from ridewise.llm import LLMError

    def broken(*args, **kwargs):
        raise LLMError("no API key")

    monkeypatch.setattr("ridewise.agent.nodes.chat_json", broken)
    monkeypatch.setattr("ridewise.agent.nodes.chat", broken)

    plan = plan_ride(
        raw_request="Twisty backroads tomorrow, about 250 km please",
        bike=f.bike(),
        profile=f.profile(),
        start_place="Lviv",
        distance_km=250,
        ride_date=RIDE_DATE,
        today=date.today(),
    )

    assert plan.route.geometry
    assert plan.weather is not None
    assert plan.gear == []
    assert plan.briefing == ""
    assert any("free-text" in w for w in plan.warnings)
    assert any("gear checklist" in w for w in plan.warnings)


def test_an_empty_garage_fails_clearly(mocked_services, fake_llm):
    with pytest.raises(PlannerFailure, match="garage is empty"):
        plan_ride(bike=None, profile=f.profile(), start_place="Lviv", ride_date=RIDE_DATE)


def test_a_past_date_is_corrected_with_a_warning(mocked_services, fake_llm):
    # No free text, so intake takes the form date rather than asking the model.
    plan = plan_ride(
        bike=f.bike(),
        profile=f.profile(),
        start_place="Lviv",
        distance_km=250,
        ride_date=date.today() - timedelta(days=5),
        today=date.today(),
    )
    assert plan.request.ride_date == date.today()
    assert any("past" in w for w in plan.warnings)
