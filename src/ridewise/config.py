"""Application settings, loaded from the environment and `.env`."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# LiteLLM reads ANTHROPIC_API_KEY and Langfuse reads LANGFUSE_* straight from the
# process environment, and pydantic-settings does not put `.env` values there.
# Loading it here, before any of them are constructed, is what makes `.env` work
# for provider credentials as well as for our own settings.
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Settings(BaseSettings):
    """Every knob RideWise reads at startup.

    Prefixed vars (`RIDEWISE_*`) are ours; unprefixed ones (`ANTHROPIC_API_KEY`,
    `LANGFUSE_*`) are read by LiteLLM and Langfuse straight from the environment,
    so they are declared here only to validate that they are present.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="RIDEWISE_",
        extra="ignore",
    )

    # --- LLM, via LiteLLM -------------------------------------------------
    llm_model: str = "anthropic/claude-opus-5-5"
    llm_max_tokens: int = 8_000
    # Opus 5.5 / Sonnet 5.5 reject temperature & top_p with a 400, so we send no
    # sampling params by default. Set this only when pointing at an older model.
    llm_temperature: float | None = None

    # --- OpenRouteService: routing + geocoding ---------------------------
    ors_api_key: str | None = None
    ors_base_url: str = "https://api.openrouteservice.org"
    # Public ORS plan: 6000 km max per route, 50 waypoints, 40 req/min.
    ors_profile: str = "driving-car"

    # --- Open-Meteo: forecast (no key needed) ----------------------------
    open_meteo_url: str = "https://api.open-meteo.com/v1/forecast"

    # --- Overpass: fuel stations from OpenStreetMap ----------------------
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    # --- Storage ----------------------------------------------------------
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'ridewise.db'}"

    # --- Planner tuning ---------------------------------------------------
    candidate_count: int = 4
    waypoints_per_loop: int = 6
    route_fit_attempts: int = 3
    route_fit_tolerance: float = 0.12
    weather_sample_points: int = 5
    http_timeout: float = 45.0

    @property
    def db_path(self) -> Path | None:
        """Filesystem path behind `database_url`, when it is SQLite."""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            return Path(self.database_url[len(prefix) :])
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
