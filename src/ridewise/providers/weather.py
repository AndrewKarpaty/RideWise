"""Open-Meteo forecast client.

Open-Meteo takes several locations in one request (comma-separated lat/lon), so
the whole route's forecast costs exactly one HTTP call - which is what makes the
ETA-aware weather window affordable.
"""

from __future__ import annotations

from datetime import date, datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ridewise.config import get_settings
from ridewise.geo import Point
from ridewise.models import HourlyWeather

HOURLY_VARIABLES = [
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "precipitation_probability",
    "wind_speed_10m",
    "wind_gusts_10m",
    "cloud_cover",
    "visibility",
    "weather_code",
]

# WMO weather interpretation codes, trimmed to what a rider cares about.
WEATHER_CODES: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "freezing drizzle",
    57: "heavy freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "heavy freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light showers",
    81: "showers",
    82: "violent showers",
    85: "light snow showers",
    86: "snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with heavy hail",
}

WET_CODES = frozenset(range(51, 100))


def describe_code(code: int) -> str:
    return WEATHER_CODES.get(int(code), f"code {code}")


class WeatherError(RuntimeError):
    """Open-Meteo refused or returned something unusable."""


class PointForecast:
    """Hourly series for one location, indexed by the hour it applies to."""

    def __init__(self, lat: float, lon: float, hours: list[HourlyWeather], utc_offset_s: int):
        self.lat = lat
        self.lon = lon
        self.hours = hours
        self.utc_offset_s = utc_offset_s
        self._by_hour = {h.time.replace(minute=0, second=0, microsecond=0): h for h in hours}

    def at(self, when: datetime) -> HourlyWeather | None:
        """Forecast for the hour containing `when` (local time, naive)."""
        return self._by_hour.get(when.replace(minute=0, second=0, microsecond=0))

    @property
    def covered(self) -> tuple[datetime, datetime] | None:
        if not self.hours:
            return None
        return (self.hours[0].time, self.hours[-1].time)


class WeatherClient:
    def __init__(self, client: httpx.Client | None = None):
        self.settings = get_settings()
        self._client = client or httpx.Client(timeout=self.settings.http_timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> WeatherClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=8),
        reraise=True,
    )
    def _get(self, params: dict[str, str]) -> object:
        response = self._client.get(self.settings.open_meteo_url, params=params)
        response.raise_for_status()
        return response.json()

    def forecast(
        self,
        points: list[Point],
        start: date,
        end: date | None = None,
    ) -> list[PointForecast]:
        """Hourly forecast for every point, in each point's own local time.

        `timezone=auto` is repeated once per location: Open-Meteo expects the
        parameter list to match the coordinate list when several are given.
        """
        if not points:
            return []
        end = end or start
        if end < start:
            raise WeatherError("forecast end date precedes start date")

        count = len(points)
        params = {
            "latitude": ",".join(f"{p[0]:.4f}" for p in points),
            "longitude": ",".join(f"{p[1]:.4f}" for p in points),
            "hourly": ",".join(HOURLY_VARIABLES),
            "timezone": ",".join(["auto"] * count),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "wind_speed_unit": "kmh",
        }

        payload = self._get(params)
        # One location returns an object; several return a list.
        blocks = payload if isinstance(payload, list) else [payload]
        if len(blocks) != count:
            raise WeatherError(f"asked for {count} locations, got {len(blocks)}")

        return [self._parse_block(block) for block in blocks]  # type: ignore[arg-type]

    @staticmethod
    def _parse_block(block: dict) -> PointForecast:
        if "error" in block and block.get("error"):
            raise WeatherError(str(block.get("reason", "unknown Open-Meteo error")))
        hourly = block.get("hourly") or {}
        times = hourly.get("time") or []

        def series(name: str) -> list:
            values = hourly.get(name) or []
            return list(values) + [None] * (len(times) - len(values))

        temps = series("temperature_2m")
        apparent = series("apparent_temperature")
        precip = series("precipitation")
        precip_prob = series("precipitation_probability")
        wind = series("wind_speed_10m")
        gusts = series("wind_gusts_10m")
        clouds = series("cloud_cover")
        visibility = series("visibility")
        codes = series("weather_code")

        hours: list[HourlyWeather] = []
        for i, stamp in enumerate(times):
            temp = temps[i]
            if temp is None:
                continue
            hours.append(
                HourlyWeather(
                    time=datetime.fromisoformat(stamp),
                    temperature_c=float(temp),
                    apparent_temperature_c=float(apparent[i] if apparent[i] is not None else temp),
                    precipitation_mm=float(precip[i] or 0.0),
                    precipitation_probability=float(precip_prob[i] or 0.0),
                    wind_speed_kmh=float(wind[i] or 0.0),
                    wind_gusts_kmh=float(gusts[i] or 0.0),
                    cloud_cover=float(clouds[i] or 0.0),
                    visibility_m=float(visibility[i]) if visibility[i] is not None else None,
                    weather_code=int(codes[i] or 0),
                )
            )

        return PointForecast(
            lat=float(block.get("latitude", 0.0)),
            lon=float(block.get("longitude", 0.0)),
            hours=hours,
            utc_offset_s=int(block.get("utc_offset_seconds", 0)),
        )
