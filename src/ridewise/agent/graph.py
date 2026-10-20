"""The planner graph: a straight pipeline from free text to a finished RidePlan.

The order matters and is not arbitrary. Routes come before weather because the
forecast is sampled along each candidate's own geometry; the choice comes after
both because a good road in a storm beats nothing; fuel comes after the choice
because it only applies to the route actually taken; and the briefing comes last
because it is the one step that gets to see everything.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from datetime import date
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from ridewise.agent.nodes import (
    PlannerFailure,
    assemble,
    build_gear_list,
    choose_route,
    forecast_candidates,
    generate_candidates,
    intake,
    plan_fuel,
    write_briefing,
)
from ridewise.agent.state import PlannerState
from ridewise.db import default_motorcycle, get_profile
from ridewise.models import Motorcycle, RidePlan, RiderProfile
from ridewise.observability import configure_observability, flush, langfuse_configured

logger = logging.getLogger(__name__)

NODE_LABELS = {
    "intake": "Reading the request",
    "routes": "Building candidate loops",
    "weather": "Checking the weather window",
    "choose": "Choosing the best ride",
    "fuel": "Planning fuel stops",
    "gear": "Writing the gear checklist",
    "briefing": "Writing your briefing",
    "assemble": "Finishing up",
}


@lru_cache(maxsize=1)
def build_graph() -> Any:
    """Compile the planner once per process."""
    graph = StateGraph(PlannerState)

    graph.add_node("intake", intake)
    graph.add_node("routes", generate_candidates)
    graph.add_node("weather", forecast_candidates)
    graph.add_node("choose", choose_route)
    graph.add_node("fuel", plan_fuel)
    graph.add_node("gear", build_gear_list)
    graph.add_node("briefing", write_briefing)
    graph.add_node("assemble", assemble)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "routes")
    graph.add_edge("routes", "weather")
    graph.add_edge("weather", "choose")
    graph.add_edge("choose", "fuel")
    graph.add_edge("fuel", "gear")
    graph.add_edge("gear", "briefing")
    graph.add_edge("briefing", "assemble")
    graph.add_edge("assemble", END)

    return graph.compile()


def _initial_state(
    *,
    raw_request: str = "",
    bike: Motorcycle | None = None,
    profile: RiderProfile | None = None,
    start_place: str = "",
    distance_km: float = 250,
    ride_date: date | None = None,
    earliest: str = "08:00",
    latest: str = "19:00",
    avoid_highways: bool = True,
    prefer_twisty: bool = True,
    today: date | None = None,
) -> PlannerState:
    profile = profile or get_profile()
    bike = bike or default_motorcycle()
    if bike is None:
        raise PlannerFailure(
            "Your garage is empty. Add a motorcycle first - the plan depends on its "
            "tank, tyres and wind protection."
        )
    if not start_place:
        start_place = profile.home_label or ""

    return PlannerState(
        raw_request=raw_request,
        today=today or date.today(),
        bike=bike,
        profile=profile,
        form_start_place=start_place,
        form_distance_km=distance_km,
        form_ride_date=ride_date or date.today(),
        form_earliest=earliest,
        form_latest=latest,
        form_avoid_highways=avoid_highways,
        form_prefer_twisty=prefer_twisty,
        warnings=[],
        progress=[],
    )


def _run(initial: PlannerState) -> Iterator[tuple[str, dict]]:
    """Stream node-by-node updates so a UI can show progress as it happens."""
    configure_observability()
    graph = build_graph()
    try:
        for chunk in graph.stream(initial, stream_mode="updates"):
            for node, update in chunk.items():
                yield node, update or {}
    finally:
        flush()


def plan_ride_stream(**kwargs: Any) -> Iterator[tuple[str, dict]]:
    """Yield `(node, update)` for each completed node. The last `assemble`
    update carries the finished `plan`."""
    yield from _run(_initial_state(**kwargs))


def plan_ride(*, on_progress: Callable[[str, dict], None] | None = None, **kwargs: Any) -> RidePlan:
    """Run the planner to completion and return the plan.

    `on_progress(node, update)` is called after each node, which is what the
    Streamlit app uses to tick its status list along.
    """
    plan: RidePlan | None = None
    for node, update in _run(_initial_state(**kwargs)):
        if on_progress is not None:
            on_progress(node, update)
        if "plan" in update:
            plan = update["plan"]

    if plan is None:
        raise PlannerFailure("The planner finished without producing a plan.")
    return plan


def tracing_enabled() -> bool:
    return langfuse_configured()
