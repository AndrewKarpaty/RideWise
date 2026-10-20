"""The geodesy the route generator depends on."""

from __future__ import annotations

import pytest

from ridewise import geo

LVIV = (49.8397, 24.0297)
KYIV = (50.4501, 30.5234)


def test_haversine_matches_known_distance():
    # Lviv to Kyiv is about 467 km great-circle.
    assert geo.haversine_km(LVIV, KYIV) == pytest.approx(467, abs=5)


def test_haversine_is_zero_for_identical_points():
    assert geo.haversine_km(LVIV, LVIV) == pytest.approx(0.0, abs=1e-9)


def test_destination_point_round_trips():
    for bearing in (0, 45, 123, 270, 359):
        moved = geo.destination_point(LVIV, bearing, 80)
        assert geo.haversine_km(LVIV, moved) == pytest.approx(80, rel=1e-3)
        assert geo.initial_bearing(LVIV, moved) == pytest.approx(bearing, abs=0.5)


def test_destination_point_normalises_longitude():
    # Crossing the antimeridian must stay inside [-180, 180].
    point = geo.destination_point((0.0, 179.5), 90, 200)
    assert -180 <= point[1] <= 180


def test_bearing_delta_takes_the_short_way_round():
    assert geo.bearing_delta(350, 10) == pytest.approx(20)
    assert geo.bearing_delta(10, 350) == pytest.approx(-20)
    # A half-turn is sign-ambiguous; only the magnitude is meaningful.
    assert abs(geo.bearing_delta(0, 180)) == pytest.approx(180)


def test_point_at_km_interpolates_and_clamps():
    path = [(0.0, 0.0), (0.0, 1.0)]
    total = geo.path_length_km(path)

    assert geo.point_at_km(path, 0) == path[0]
    assert geo.point_at_km(path, -5) == path[0]
    assert geo.point_at_km(path, total + 50) == path[-1]

    middle = geo.point_at_km(path, total / 2)
    assert middle[1] == pytest.approx(0.5, abs=1e-6)


def test_sample_along_includes_both_ends():
    path = [(0.0, 0.0), (0.0, 0.5), (0.0, 1.0)]
    samples = geo.sample_along(path, 5)

    assert len(samples) == 5
    assert samples[0][1] == path[0]
    assert samples[-1][1] == path[-1]
    distances = [d for d, _ in samples]
    assert distances == sorted(distances)


def test_twistiness_separates_straight_from_winding():
    straight = [geo.destination_point(LVIV, 90, km) for km in range(0, 40)]

    # A sawtooth that keeps reversing direction every kilometre.
    winding = [LVIV]
    for i in range(40):
        winding.append(geo.destination_point(winding[-1], 60 if i % 2 else 120, 1.0))

    assert geo.twistiness(straight) < 1.0
    assert geo.twistiness(winding) > 20.0


def test_twistiness_handles_degenerate_input():
    assert geo.twistiness([]) == 0.0
    assert geo.twistiness([LVIV]) == 0.0
    assert geo.twistiness([LVIV, KYIV]) == 0.0


def test_loop_waypoints_form_a_ring_that_returns_home():
    radius = 30.0
    waypoints = geo.loop_waypoints(LVIV, radius, 90, 6)
    centre = geo.destination_point(LVIV, 90, radius)

    assert len(waypoints) == 6
    # Every waypoint sits on the circle, and so does the start.
    for point in waypoints:
        assert geo.haversine_km(centre, point) == pytest.approx(radius, rel=1e-3)
    assert geo.haversine_km(centre, LVIV) == pytest.approx(radius, rel=1e-3)

    # The far side of the loop is roughly two radii out.
    assert max(geo.haversine_km(LVIV, p) for p in waypoints) == pytest.approx(2 * radius, rel=0.05)


def test_loop_waypoints_rejects_too_few_points():
    with pytest.raises(ValueError):
        geo.loop_waypoints(LVIV, 30, 0, 1)


def test_radius_for_target_distance_predicts_the_polygon():
    target, count = 250.0, 6
    radius = geo.radius_for_target_distance(target, count, winding=1.25)

    ring = [LVIV, *geo.loop_waypoints(LVIV, radius, 45, count), LVIV]
    # The straight-line ring is the target divided by the winding allowance.
    assert geo.path_length_km(ring) == pytest.approx(target / 1.25, rel=0.02)


def test_bbox_covers_every_point():
    points = [LVIV, KYIV, (48.0, 22.0)]
    south, west, north, east = geo.bbox(points)
    for lat, lon in points:
        assert south <= lat <= north
        assert west <= lon <= east
