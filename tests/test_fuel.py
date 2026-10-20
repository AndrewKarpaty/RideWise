"""Turning a route plus a tank into a refuelling plan."""

from __future__ import annotations

from ridewise.geo import cumulative_km, point_at_km
from ridewise.models import FuelStop
from ridewise.providers.fuel import plan_fuel_stops
from tests import factories as f


def _stations_every(geometry, spacing_km: float) -> list[FuelStop]:
    """A station exactly on the route every `spacing_km`."""
    total = cumulative_km(geometry)[-1]
    stops = []
    km = spacing_km
    while km < total:
        lat, lon = point_at_km(geometry, km)
        stops.append(FuelStop(name=f"Station km {km:.0f}", lat=lat, lon=lon, distance_along_km=km))
        km += spacing_km
    return stops


def test_no_stop_needed_when_the_route_fits_the_tank():
    geometry = f.ring_geometry(radius_km=20)  # ~126 km
    bike = f.bike(tank=16, consumption=4.3, reserve=2.5)  # ~314 km usable

    stops, warnings = plan_fuel_stops(geometry, bike, stations=[])

    assert stops == []
    assert warnings == []


def test_a_long_route_gets_a_stop_before_the_tank_runs_dry():
    geometry = f.ring_geometry(radius_km=60)  # ~377 km
    bike = f.bike(tank=16, consumption=4.3, reserve=2.5)  # ~314 km usable
    stations = _stations_every(geometry, 40)

    stops, warnings = plan_fuel_stops(geometry, bike, stations=stations)

    assert warnings == []
    assert len(stops) == 1
    # Must be inside the safe range, and far enough along to be useful.
    assert stops[0].distance_along_km <= bike.range_km * 0.85
    assert stops[0].distance_along_km > 200
    assert "still to ride" in stops[0].reason


def test_a_thirsty_bike_needs_several_stops_in_order():
    geometry = f.ring_geometry(radius_km=80)  # ~503 km
    bike = f.bike(tank=12, consumption=6.0, reserve=2.0)  # ~167 km usable
    stations = _stations_every(geometry, 25)

    stops, warnings = plan_fuel_stops(geometry, bike, stations=stations)

    assert warnings == []
    assert len(stops) >= 3
    marks = [s.distance_along_km for s in stops]
    assert marks == sorted(marks)
    # No leg between consecutive stops may exceed the safe range.
    safe = bike.range_km * 0.85
    previous = 0.0
    for mark in marks:
        assert mark - previous <= safe + 1e-6
        previous = mark


def test_a_gap_with_no_stations_is_reported_not_hidden():
    geometry = f.ring_geometry(radius_km=60)  # ~377 km
    bike = f.bike(tank=16, consumption=4.3, reserve=2.5)
    # Stations only in the first 50 km, nothing in reach later.
    stations = [s for s in _stations_every(geometry, 20) if s.distance_along_km <= 50]

    stops, warnings = plan_fuel_stops(geometry, bike, stations=stations)

    assert warnings, "the rider must be told the stretch cannot be covered"
    assert "cannot cover" in warnings[0]
    assert len(stops) <= 1


def test_no_stations_at_all_warns_to_carry_fuel():
    geometry = f.ring_geometry(radius_km=60)
    bike = f.bike(tank=16, consumption=4.3, reserve=2.5)

    stops, warnings = plan_fuel_stops(geometry, bike, stations=[])

    assert stops == []
    assert "Carry fuel" in warnings[0]


def test_a_bike_with_no_usable_range_is_flagged():
    geometry = f.ring_geometry(radius_km=60)
    bike = f.bike(tank=5, consumption=4.0, reserve=5.0)  # reserve swallows the tank

    stops, warnings = plan_fuel_stops(geometry, bike, stations=[])

    assert stops == []
    assert "no usable range" in warnings[0]


def test_degenerate_geometry_is_handled():
    assert plan_fuel_stops([], f.bike()) == ([], [])
