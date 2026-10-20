"""Headless render of the Streamlit app.

`AppTest` executes the real app script, so this catches the mistakes a unit test
cannot: a bad widget argument, a broken format string, an import that only fires
inside a page function.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

# AppTest resolves a relative path against the calling file, so be explicit.
APP = str(Path(__file__).resolve().parents[1] / "src" / "ridewise" / "ui" / "app.py")
TIMEOUT = 60


def _run(**session_state) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=TIMEOUT)
    for key, value in session_state.items():
        app.session_state[key] = value
    return app.run()


@pytest.fixture(autouse=True)
def _seeded_garage():
    """Every page is exercised against a garage with bikes in it."""
    from ridewise.seed import seed

    seed()


def test_plan_page_renders():
    app = _run()
    assert not app.exception
    # The sidebar brand and the form's primary action both made it to the page.
    assert any("RideWise" in t.value for t in app.sidebar.title)
    assert any(b.label == "Plan my ride" for b in app.button)


def test_plan_page_warns_when_the_routing_key_is_missing(monkeypatch):
    monkeypatch.delenv("RIDEWISE_ORS_API_KEY", raising=False)
    from ridewise.config import get_settings

    get_settings.cache_clear()

    app = _run()
    assert not app.exception
    assert any("OpenRouteService" in e.value for e in app.error)
    # And the button must be disabled rather than failing mid-plan.
    assert all(b.disabled for b in app.button if b.label == "Plan my ride")


def test_garage_page_lists_the_seeded_bikes():
    app = _run(nav="Garage")
    assert not app.exception

    # Each bike is an expander titled with its nickname, plus an "add" one.
    labels = [e.label for e in app.get("expander")]
    assert any("Tenere" in label for label in labels)
    assert any("Street Triple" in label for label in labels)
    assert any("Add a motorcycle" in label for label in labels)

    # The live range preview inside the form does the fuel maths.
    captions = " ".join(c.value for c in app.caption)
    assert "314 km" in captions, "the Tenere's usable range should be shown"


def test_profile_page_renders_service_status():
    app = _run(nav="Rider profile")
    assert not app.exception
    assert any("Rider profile" in t.value for t in app.title)


def test_history_page_renders_empty_state():
    app = _run(nav="History")
    assert not app.exception
    assert any("No saved plans" in i.value for i in app.info)


def test_a_stored_plan_renders_without_error(monkeypatch):
    """The results half of the page - map, metrics, gear, briefing."""
    from datetime import date, datetime, timedelta

    from ridewise.models import FuelStop, GearItem, RidePlan, WeatherWindow
    from tests import factories as f

    route = f.route()
    day = date.today() + timedelta(days=1)
    legs = []
    from ridewise.geo import sample_along
    from ridewise.models import LegForecast

    for i, (km, point) in enumerate(sample_along(route.geometry, 5)):
        legs.append(
            LegForecast(
                distance_along_km=km,
                lat=point[0],
                lon=point[1],
                eta=datetime.combine(day, datetime.min.time()).replace(hour=9 + i),
                weather=f.hour(datetime.combine(day, datetime.min.time()).replace(hour=9 + i)),
            )
        )

    window = WeatherWindow(
        departure=datetime.combine(day, datetime.min.time()).replace(hour=9),
        arrival=datetime.combine(day, datetime.min.time()).replace(hour=15),
        score=82.0,
        rain_risk_pct=10,
        min_temp_c=14,
        max_temp_c=21,
        max_gust_kmh=25,
        total_precipitation_mm=0.0,
        verdict="Good - ride it",
        legs=legs,
    )
    plan = RidePlan(
        request=f.request(ride_date=day),
        bike_label="Yamaha Tenere 700 (2023)",
        route=route,
        alternatives=[f.route(candidate_id="c2", bearing_deg=200, twistiness=18)],
        weather=window,
        weather_options=[window],
        fuel_stops=[
            FuelStop(
                name="OKKO",
                lat=route.geometry[50][0],
                lon=route.geometry[50][1],
                distance_along_km=140.0,
                detour_km=0.4,
                reason="km 140 - last station in range",
            )
        ],
        gear=[
            GearItem(item="Mesh jacket with liner", reason="14-21C swing", essential=True),
            GearItem(item="Sunglasses", reason="Low sun on the return leg", essential=False),
        ],
        briefing="Leave at nine and you will have the pass to yourself.",
        warnings=["Example warning, shown as a banner."],
    )

    app = _run(plan=plan.model_dump_json())
    assert not app.exception

    text = " ".join(m.value for m in app.markdown)
    assert "Leave at 09:00" in text
    assert any("Your briefing" in h.value for h in app.subheader)
    assert any("Gear checklist" in h.value for h in app.subheader)
    # Metrics are present and the checklist is interactive.
    assert len(app.metric) >= 4
    assert len(app.checkbox) >= 2
