"""Seed the garage so a fresh clone has something to plan with."""

from __future__ import annotations

from ridewise.db import get_profile, list_motorcycles, save_motorcycle, save_profile
from ridewise.models import BikeCategory, Motorcycle, TireType, WindProtection


def starter_bikes() -> list[Motorcycle]:
    """Fresh instances on every call.

    These must not be module-level constants: once an instance has been through
    a session it is detached and its attributes are expired, so reusing it
    raises DetachedInstanceError the second time around.
    """
    return [
        Motorcycle(
            nickname="Tenere",
            make="Yamaha",
            model="Tenere 700",
            year=2023,
            category=BikeCategory.ADVENTURE,
            tank_liters=16.0,
            consumption_l_per_100km=4.3,
            reserve_liters=2.5,
            wind_protection=WindProtection.LOW,
            tire_type=TireType.DUAL_SPORT,
            heated_grips=False,
            has_luggage=True,
            notes="Soft panniers fitted. Screen is short - windblast above 110 km/h.",
            is_default=True,
        ),
        Motorcycle(
            nickname="Street Triple",
            make="Triumph",
            model="Street Triple 765 RS",
            year=2021,
            category=BikeCategory.NAKED,
            tank_liters=17.4,
            consumption_l_per_100km=5.6,
            reserve_liters=3.0,
            wind_protection=WindProtection.NONE,
            tire_type=TireType.SPORT,
            heated_grips=False,
            has_luggage=False,
            notes="No wind protection and sport tyres - unhappy below 10 C or in the wet.",
        ),
    ]


def seed() -> None:
    if list_motorcycles():
        print("Garage already has bikes; leaving it alone.")
    else:
        for bike in starter_bikes():
            saved = save_motorcycle(bike)
            print(f"Added {saved.label} ({saved.range_km:.0f} km usable range)")

    profile = get_profile()
    if not profile.home_label:
        profile.home_label = "Lviv, Ukraine"
        profile.home_lat = 49.8397
        profile.home_lon = 24.0297
        save_profile(profile)
        print(f"Set home base to {profile.home_label}")
    else:
        print(f"Home base already set to {profile.home_label}")


if __name__ == "__main__":
    seed()
