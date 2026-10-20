"""Scoring, the weather window, and the ETA logic that makes it meaningful."""

from __future__ import annotations

from datetime import datetime, time

import pytest

from ridewise import planner
from tests import factories as f


class TestRideability:
    def test_a_clear_mild_hour_scores_full_marks(self):
        score, reasons = planner.rideability(f.hour(datetime(2026, 6, 20, 12)), f.profile())
        assert score == 100.0
        assert reasons == []

    def test_rain_is_penalised_and_explained(self):
        score, reasons = planner.rideability(
            f.hour(datetime(2026, 6, 20, 12), rain_pct=90, rain_mm=3.0, code=65), f.profile()
        )
        assert score < 30
        assert any("rain" in r for r in reasons)

    def test_a_rider_who_accepts_rain_is_penalised_less(self):
        wet = f.hour(datetime(2026, 6, 20, 12), rain_pct=80, rain_mm=1.0, code=63)
        fussy, _ = planner.rideability(wet, f.profile(accepts_rain=False))
        relaxed, _ = planner.rideability(wet, f.profile(accepts_rain=True))
        assert relaxed > fussy

    def test_cold_is_measured_against_the_rider_not_a_constant(self):
        chilly = f.hour(datetime(2026, 6, 20, 7), temp=6.0)
        hardy, _ = planner.rideability(chilly, f.profile(min_temp=0.0))
        soft, _ = planner.rideability(chilly, f.profile(min_temp=15.0))
        assert hardy > soft

    def test_ice_risk_is_called_out(self):
        _, reasons = planner.rideability(
            f.hour(datetime(2026, 1, 20, 9), temp=0.0, rain_pct=60, code=66), f.profile()
        )
        assert any("ice" in r for r in reasons)

    def test_score_never_goes_negative(self):
        score, _ = planner.rideability(
            f.hour(
                datetime(2026, 1, 20, 9), temp=-15, rain_pct=100, rain_mm=20, gusts=120, code=99
            ),
            f.profile(),
        )
        assert score == 0.0


class TestRouteScoring:
    def test_twisty_preference_rewards_turning(self):
        request = f.request(prefer_twisty=True)
        straight = f.route(twistiness=2.0)
        curvy = f.route(twistiness=50.0)
        assert planner.score_route(curvy, request) > planner.score_route(straight, request)

    def test_distance_accuracy_matters_more_when_not_chasing_corners(self):
        request = f.request(target_distance_km=250, prefer_twisty=False)
        on_target = f.route(distance_km=250, twistiness=10)
        way_off = f.route(distance_km=400, twistiness=10)
        assert planner.score_route(on_target, request) > planner.score_route(way_off, request)

    def test_score_stays_in_range(self):
        request = f.request()
        extreme = f.route(distance_km=250, twistiness=500, ascent_m=50_000)
        assert 0 <= planner.score_route(extreme, request) <= 100


class TestDepartures:
    def test_only_departures_that_finish_in_time_are_offered(self):
        request = f.request(earliest=time(8, 0), latest=time(14, 0))
        route = f.route(duration_h=4.0)  # 5 h elapsed with the stop factor

        departures = planner.candidate_departures(request, route)

        assert departures[0].hour == 8
        latest_allowed = datetime.combine(request.ride_date, request.latest_return)
        for departure in departures:
            assert departure.hour + planner.elapsed_hours(route) <= latest_allowed.hour + 0.01

    def test_a_day_too_short_still_offers_the_earliest_start(self):
        request = f.request(earliest=time(9, 0), latest=time(10, 0))
        departures = planner.candidate_departures(request, f.route(duration_h=6.0))
        assert len(departures) == 1
        assert departures[0].hour == 9


class TestWeatherWindow:
    def test_window_scores_each_point_at_its_own_eta(self):
        """The whole point of the design: a front arriving mid-ride must show up
        on the later legs only."""
        request = f.request()
        route = f.route(duration_h=4.0)
        # Rain from 13:00 onwards at every sample point.
        forecasts = [f.forecast(request.ride_date, rain_from_hour=13) for _ in range(5)]

        window = planner.build_window(
            route, forecasts, datetime.combine(request.ride_date, time(10, 0)), f.profile()
        )

        assert window is not None
        etas = [leg.eta for leg in window.legs]
        assert etas == sorted(etas), "legs must be ordered in time"
        dry = [leg for leg in window.legs if leg.eta.hour < 13]
        wet = [leg for leg in window.legs if leg.eta.hour >= 13]
        assert dry and wet, "this fixture should straddle the front"
        assert all(leg.weather.precipitation_probability == 0 for leg in dry)
        assert all(leg.weather.precipitation_probability == 95 for leg in wet)

    def test_an_earlier_start_beats_the_front(self):
        request = f.request()
        route = f.route(duration_h=3.0)
        forecasts = [f.forecast(request.ride_date, rain_from_hour=14) for _ in range(5)]

        early = planner.build_window(
            route, forecasts, datetime.combine(request.ride_date, time(8, 0)), f.profile()
        )
        late = planner.build_window(
            route, forecasts, datetime.combine(request.ride_date, time(13, 0)), f.profile()
        )

        assert early is not None and late is not None
        assert early.score > late.score

    def test_best_windows_are_sorted_and_capped(self):
        request = f.request()
        route = f.route(duration_h=3.0)
        forecasts = [f.forecast(request.ride_date, rain_from_hour=14) for _ in range(5)]

        windows = planner.best_windows(route, forecasts, request, f.profile(), limit=3)

        assert len(windows) == 3
        assert [w.score for w in windows] == sorted((w.score for w in windows), reverse=True)

    def test_window_is_none_when_the_forecast_does_not_reach(self):
        request = f.request()
        route = f.route(duration_h=4.0)
        forecasts = [f.forecast(request.ride_date, hours=2) for _ in range(5)]

        window = planner.build_window(
            route, forecasts, datetime.combine(request.ride_date, time(10, 0)), f.profile()
        )
        assert window is None

    def test_worst_leg_drags_the_score_below_the_mean(self):
        request = f.request()
        route = f.route(duration_h=4.0)
        # Only the final sample point is wet.
        forecasts = [f.forecast(request.ride_date) for _ in range(4)]
        forecasts.append(f.forecast(request.ride_date, rain_from_hour=0))

        window = planner.build_window(
            route, forecasts, datetime.combine(request.ride_date, time(9, 0)), f.profile()
        )

        assert window is not None
        leg_scores = [planner.rideability(leg.weather, f.profile())[0] for leg in window.legs]
        assert window.score < sum(leg_scores) / len(leg_scores)


def test_combined_score_prefers_good_weather_over_good_roads():
    great_roads_bad_weather = planner.combined_score(95.0, _window(score=20))
    ok_roads_great_weather = planner.combined_score(65.0, _window(score=95))
    assert ok_roads_great_weather > great_roads_bad_weather


def test_combined_score_discounts_a_route_with_no_forecast():
    assert planner.combined_score(80.0, None) == pytest.approx(40.0)


def _window(*, score: float):
    from ridewise.models import WeatherWindow

    return WeatherWindow(
        departure=datetime(2026, 6, 20, 9),
        arrival=datetime(2026, 6, 20, 15),
        score=score,
        rain_risk_pct=0,
        min_temp_c=15,
        max_temp_c=22,
        max_gust_kmh=20,
        total_precipitation_mm=0,
    )
