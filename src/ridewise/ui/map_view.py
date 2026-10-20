"""Folium map rendering for a ride plan."""

from __future__ import annotations

import folium

from ridewise.geo import bbox
from ridewise.models import RidePlan, RouteCandidate
from ridewise.providers.weather import WET_CODES, describe_code

ROUTE_COLOUR = "#e8590c"
ALT_COLOUR = "#868e96"


def _weather_icon(code: int, precipitation_probability: float) -> tuple[str, str]:
    """(font-awesome icon, colour) for a leg marker."""
    if code in {95, 96, 99}:
        return "bolt", "red"
    if code in {71, 73, 75, 77, 85, 86, 66, 67, 56, 57}:
        return "snowflake", "lightblue"
    if code in WET_CODES:
        return "cloud-rain", "blue"
    if code in {45, 48}:
        return "smog", "gray"
    if precipitation_probability >= 40:
        return "cloud", "cadetblue"
    if code in {0, 1}:
        return "sun", "orange"
    return "cloud", "lightgray"


def build_map(plan: RidePlan, *, show_alternatives: bool = True) -> folium.Map:
    """The ride map: route, start, fuel stops and the forecast along the way."""
    route = plan.route
    centre = (
        route.geometry[len(route.geometry) // 2] if route.geometry else plan.request.start.point
    )

    fmap = folium.Map(location=list(centre), zoom_start=9, tiles=None, control_scale=True)
    # Both tile sets are keyless. CartoDB's basemaps now require an API key, so
    # they are deliberately not offered - that layer would render blank.
    folium.TileLayer("OpenStreetMap", name="Streets").add_to(fmap)
    folium.TileLayer(
        tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attr="OpenTopoMap (CC-BY-SA)",
        name="Terrain",
        max_zoom=17,
    ).add_to(fmap)

    if show_alternatives and plan.alternatives:
        alt_layer = folium.FeatureGroup(name="Alternative loops", show=False)
        for alt in plan.alternatives:
            if not alt.geometry:
                continue
            folium.PolyLine(
                [list(p) for p in alt.geometry],
                color=ALT_COLOUR,
                weight=3,
                opacity=0.55,
                dash_array="6",
                tooltip=f"{alt.name} - roads {alt.road_score:.0f}/100",
            ).add_to(alt_layer)
        alt_layer.add_to(fmap)

    route_layer = folium.FeatureGroup(name="Chosen route")
    if route.geometry:
        folium.PolyLine(
            [list(p) for p in route.geometry],
            color=ROUTE_COLOUR,
            weight=5,
            opacity=0.9,
            tooltip=(
                f"{route.distance_km:.0f} km - {route.twistiness:.0f} deg/km - "
                f"{route.ascent_m:.0f} m climb"
            ),
        ).add_to(route_layer)
    route_layer.add_to(fmap)

    folium.Marker(
        list(plan.request.start.point),
        tooltip=f"Start & finish: {plan.request.start.label}",
        icon=folium.Icon(color="darkred", icon="motorcycle", prefix="fa"),
    ).add_to(fmap)

    if plan.weather and plan.weather.legs:
        weather_layer = folium.FeatureGroup(name="Weather along the route")
        for leg in plan.weather.legs:
            hour = leg.weather
            icon, colour = _weather_icon(hour.weather_code, hour.precipitation_probability)
            folium.Marker(
                [leg.lat, leg.lon],
                tooltip=(
                    f"km {leg.distance_along_km:.0f} at {leg.eta.strftime('%H:%M')}<br>"
                    f"{describe_code(hour.weather_code)}, "
                    f"{hour.temperature_c:.0f}&deg;C "
                    f"(feels {hour.apparent_temperature_c:.0f}&deg;C)<br>"
                    f"rain {hour.precipitation_probability:.0f}%, "
                    f"gusts {hour.wind_gusts_kmh:.0f} km/h"
                ),
                icon=folium.Icon(color=colour, icon=icon, prefix="fa"),
            ).add_to(weather_layer)
        weather_layer.add_to(fmap)

    if plan.fuel_stops:
        fuel_layer = folium.FeatureGroup(name="Fuel stops")
        for stop in plan.fuel_stops:
            folium.Marker(
                [stop.lat, stop.lon],
                tooltip=(
                    f"{stop.name}<br>km {stop.distance_along_km:.0f}"
                    + (f"<br>{stop.detour_km * 1000:.0f} m off route" if stop.detour_km else "")
                ),
                icon=folium.Icon(color="green", icon="gas-pump", prefix="fa"),
            ).add_to(fuel_layer)
        fuel_layer.add_to(fmap)

    folium.LayerControl(collapsed=True).add_to(fmap)

    if route.geometry:
        south, west, north, east = bbox(route.geometry)
        fmap.fit_bounds([[south, west], [north, east]], padding=(20, 20))

    return fmap


def build_preview_map(candidates: list[RouteCandidate], start: tuple[float, float]) -> folium.Map:
    """All candidate loops at once - useful while debugging the generator."""
    fmap = folium.Map(location=list(start), zoom_start=9, control_scale=True)
    palette = ["#e8590c", "#1c7ed6", "#2f9e44", "#ae3ec9", "#f08c00", "#495057"]
    all_points: list[tuple[float, float]] = []

    for i, candidate in enumerate(candidates):
        if not candidate.geometry:
            continue
        all_points.extend(candidate.geometry)
        folium.PolyLine(
            [list(p) for p in candidate.geometry],
            color=palette[i % len(palette)],
            weight=4,
            opacity=0.8,
            tooltip=f"{candidate.name} - roads {candidate.road_score:.0f}/100",
        ).add_to(fmap)

    folium.Marker(
        list(start), icon=folium.Icon(color="darkred", icon="motorcycle", prefix="fa")
    ).add_to(fmap)

    if all_points:
        south, west, north, east = bbox(all_points)
        fmap.fit_bounds([[south, west], [north, east]], padding=(20, 20))
    return fmap
