"""Outbound integrations: routing, forecast and fuel-station lookup."""

from ridewise.providers.fuel import FuelError, find_fuel_stations, plan_fuel_stops
from ridewise.providers.routing import RoutingClient, RoutingError
from ridewise.providers.weather import WeatherClient, WeatherError

__all__ = [
    "FuelError",
    "RoutingClient",
    "RoutingError",
    "WeatherClient",
    "WeatherError",
    "find_fuel_stations",
    "plan_fuel_stops",
]
