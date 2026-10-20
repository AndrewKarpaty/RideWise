"""SQLite storage for the garage and plan history."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from ridewise.config import get_settings
from ridewise.models import Motorcycle, RiderProfile, SavedPlan

_engine: Engine | None = None


def get_engine() -> Engine:
    """Process-wide engine. `check_same_thread` is off because Streamlit reruns
    the script on its own threads."""
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}
        _engine = create_engine(settings.database_url, connect_args=connect_args)
        SQLModel.metadata.create_all(_engine)
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def list_motorcycles() -> list[Motorcycle]:
    with session_scope() as session:
        # SQLModel's class attributes carry the column descriptors at runtime;
        # the annotations describe the instance values, hence the ignore.
        stmt = select(Motorcycle).order_by(
            Motorcycle.is_default.desc(),  # type: ignore[attr-defined]
            Motorcycle.nickname,
        )
        return list(session.exec(stmt))


def get_motorcycle(bike_id: int) -> Motorcycle | None:
    with session_scope() as session:
        return session.get(Motorcycle, bike_id)


def save_motorcycle(bike: Motorcycle) -> Motorcycle:
    with session_scope() as session:
        if bike.is_default:
            for other in session.exec(select(Motorcycle).where(Motorcycle.is_default)):
                if other.id != bike.id:
                    other.is_default = False
                    session.add(other)
        session.add(bike)
        session.commit()
        session.refresh(bike)
        return bike


def delete_motorcycle(bike_id: int) -> None:
    with session_scope() as session:
        bike = session.get(Motorcycle, bike_id)
        if bike:
            session.delete(bike)
            session.commit()


def default_motorcycle() -> Motorcycle | None:
    bikes = list_motorcycles()
    return bikes[0] if bikes else None


def get_profile() -> RiderProfile:
    """The single rider profile, created on first access."""
    with session_scope() as session:
        profile = session.exec(select(RiderProfile)).first()
        if profile is None:
            profile = RiderProfile()
            session.add(profile)
            session.commit()
            session.refresh(profile)
        return profile


def save_profile(profile: RiderProfile) -> RiderProfile:
    with session_scope() as session:
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile


def save_plan(plan: SavedPlan) -> SavedPlan:
    with session_scope() as session:
        session.add(plan)
        session.commit()
        session.refresh(plan)
        return plan


def list_plans(limit: int = 25) -> list[SavedPlan]:
    with session_scope() as session:
        stmt = (
            select(SavedPlan)
            .order_by(SavedPlan.created_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        return list(session.exec(stmt))
