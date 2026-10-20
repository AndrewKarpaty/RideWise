"""Storage round-trips, including the detached-instance case the API hits."""

from __future__ import annotations

from ridewise.db import (
    get_motorcycle,
    get_profile,
    list_motorcycles,
    save_motorcycle,
    save_profile,
)
from tests import factories as f


def test_save_then_read_back():
    saved = save_motorcycle(f.bike())
    assert saved.id is not None

    again = get_motorcycle(saved.id)
    assert again is not None
    assert again.nickname == "Test"
    assert again.range_km == saved.range_km


def test_editing_a_default_bike_loaded_in_another_session():
    """The API loads a bike, mutates it, and saves it from a fresh session.

    For the default bike that used to raise InvalidRequestError: clearing the
    old default pulled a row with the same primary key into the session, and
    `add` refused to attach the detached copy on top of it.
    """
    bike = f.bike()
    bike.is_default = True
    first = save_motorcycle(bike)
    assert first.id is not None

    # Exactly what `PUT /api/bikes/{id}` and the photo upload do.
    detached = get_motorcycle(first.id)
    assert detached is not None
    detached.photo_path = "bike-1.png"
    detached.nickname = "Renamed"

    updated = save_motorcycle(detached)

    assert updated.nickname == "Renamed"
    assert updated.photo_path == "bike-1.png"
    assert updated.is_default is True
    assert len(list_motorcycles()) == 1


def test_only_one_bike_stays_default():
    first = save_motorcycle(f.bike())
    first.is_default = True
    save_motorcycle(first)

    second = f.bike()
    second.nickname = "Second"
    second.is_default = True
    save_motorcycle(second)

    defaults = [b for b in list_motorcycles() if b.is_default]
    assert len(defaults) == 1
    assert defaults[0].nickname == "Second"


def test_profile_is_created_once_and_updates_in_place():
    profile = get_profile()
    assert profile.id is not None

    profile.min_comfortable_temp_c = 2.0
    profile.home_label = "Lviv, Ukraine"
    saved = save_profile(profile)

    assert saved.id == profile.id
    assert get_profile().min_comfortable_temp_c == 2.0

    # A second read must not create a second row.
    again = get_profile()
    assert again.id == profile.id
