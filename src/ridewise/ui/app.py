"""RideWise Streamlit app.

Run with: streamlit run src/ridewise/ui/app.py
"""

from __future__ import annotations

import sys
from datetime import date, time, timedelta
from pathlib import Path

# Allow `streamlit run src/ridewise/ui/app.py` from a clone without installing.
if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from streamlit_folium import st_folium

from ridewise.agent.graph import NODE_LABELS, plan_ride_stream, tracing_enabled
from ridewise.agent.nodes import PlannerFailure
from ridewise.config import get_settings
from ridewise.db import (
    delete_motorcycle,
    get_profile,
    list_motorcycles,
    list_plans,
    save_motorcycle,
    save_plan,
    save_profile,
)
from ridewise.models import (
    BikeCategory,
    Experience,
    Motorcycle,
    RidePlan,
    SavedPlan,
    TireType,
    WindProtection,
)
from ridewise.providers.weather import describe_code
from ridewise.ui.map_view import build_map

st.set_page_config(
    page_title="RideWise",
    page_icon="\N{RACING MOTORCYCLE}",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _score_colour(score: float) -> str:
    if score >= 80:
        return "#2f9e44"
    if score >= 60:
        return "#f08c00"
    if score >= 40:
        return "#e8590c"
    return "#c92a2a"


def _setup_banner() -> bool:
    """Warn about missing credentials. Returns True when planning is possible."""
    settings = get_settings()
    ready = True
    if not settings.ors_api_key:
        st.error(
            "**No OpenRouteService key.** RideWise needs one to build routes. "
            "Get a free key at https://openrouteservice.org/dev/#/signup, then put "
            "`RIDEWISE_ORS_API_KEY=...` in your `.env` and restart.",
            icon="\N{WARNING SIGN}",
        )
        ready = False
    return ready


# ---------------------------------------------------------------------------
# plan page
# ---------------------------------------------------------------------------


def _render_summary(plan: RidePlan) -> None:
    route = plan.route
    weather = plan.weather

    cols = st.columns(4)
    cols[0].metric("Distance", f"{route.distance_km:.0f} km")
    cols[1].metric(
        "Riding time",
        f"{route.moving_duration_h:.1f} h",
        help="Moving time from the router; the weather window adds time for stops.",
    )
    cols[2].metric(
        "Twistiness",
        f"{route.twistiness:.0f}\N{DEGREE SIGN}/km",
        help="Average heading change per kilometre. A motorway is near 0; a mountain "
        "pass runs 60 or more.",
    )
    cols[3].metric("Climbing", f"{route.ascent_m:.0f} m")

    if weather is None:
        st.warning("No forecast was available for this date, so there is no weather window.")
        return

    colour = _score_colour(weather.score)
    st.markdown(
        f"""
<div style="border-left:4px solid {colour};padding:0.6rem 1rem;background:rgba(128,128,128,0.08);
border-radius:4px;margin:0.5rem 0 1rem 0;">
<strong style="font-size:1.05rem;">Leave at {weather.departure.strftime("%H:%M")},
back by {weather.arrival.strftime("%H:%M")}</strong><br>
<span style="color:{colour};font-weight:600;">{weather.score:.0f}/100</span> &mdash;
{weather.verdict}<br>
<span style="opacity:0.85;">Feels like {weather.min_temp_c:.0f} to
{weather.max_temp_c:.0f}&deg;C &middot; rain risk up to {weather.rain_risk_pct:.0f}%
&middot; {weather.total_precipitation_mm:.1f} mm &middot; gusts to
{weather.max_gust_kmh:.0f} km/h</span>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_weather_detail(plan: RidePlan) -> None:
    options = plan.weather_options
    if not options:
        return

    st.subheader("Departure options")
    st.caption(
        "Scored on the weather you would actually meet: each point on the loop is "
        "checked at the time you would reach it."
    )

    labels = [
        f"{w.departure.strftime('%H:%M')} \N{RIGHTWARDS ARROW} "
        f"{w.arrival.strftime('%H:%M')}  ({w.score:.0f}/100)"
        for w in options
    ]
    index = st.radio(
        "Departure",
        range(len(options)),
        format_func=lambda i: labels[i],
        horizontal=True,
        label_visibility="collapsed",
        key="departure_choice",
    )
    window = options[index]
    st.caption(window.verdict)

    rows = [
        {
            "km": round(leg.distance_along_km),
            "at": leg.eta.strftime("%H:%M"),
            "conditions": describe_code(leg.weather.weather_code),
            "temp": f"{leg.weather.temperature_c:.0f}\N{DEGREE SIGN}C",
            "feels": f"{leg.weather.apparent_temperature_c:.0f}\N{DEGREE SIGN}C",
            "rain": f"{leg.weather.precipitation_probability:.0f}%",
            "gusts": f"{leg.weather.wind_gusts_kmh:.0f} km/h",
        }
        for leg in window.legs
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)


def _render_fuel(plan: RidePlan) -> None:
    st.subheader("Fuel")
    if not plan.fuel_stops:
        st.success(
            f"No stop needed \N{EM DASH} {plan.bike_label} covers "
            f"{plan.route.distance_km:.0f} km on one tank.",
            icon="\N{FUEL PUMP}",
        )
        return
    for stop in plan.fuel_stops:
        detour = (
            f" \N{MIDDLE DOT} {stop.detour_km * 1000:.0f} m off route" if stop.detour_km else ""
        )
        st.markdown(
            f"**{stop.name}** \N{MIDDLE DOT} km {stop.distance_along_km:.0f}{detour}  \n"
            f"<span style='opacity:0.75;font-size:0.9em;'>{stop.reason}</span>",
            unsafe_allow_html=True,
        )


def _render_gear(plan: RidePlan) -> None:
    st.subheader("Gear checklist")
    if not plan.gear:
        st.info("No gear checklist was generated for this ride.")
        return

    essential = [g for g in plan.gear if g.essential]
    optional = [g for g in plan.gear if not g.essential]

    for label, items in (("Essential", essential), ("Worth packing", optional)):
        if not items:
            continue
        st.markdown(f"**{label}**")
        for i, item in enumerate(items):
            st.checkbox(
                item.item,
                key=f"gear_{label}_{i}_{item.item[:20]}",
                help=item.reason,
            )
            st.caption(item.reason)


def _render_alternatives(plan: RidePlan) -> None:
    if not plan.alternatives:
        return
    with st.expander(f"Alternative loops ({len(plan.alternatives)})"):
        st.caption("Toggle these on in the map's layer control to compare them.")
        rows = [
            {
                "loop": alt.name,
                "distance": f"{alt.distance_km:.0f} km",
                "twistiness": f"{alt.twistiness:.0f}\N{DEGREE SIGN}/km",
                "climb": f"{alt.ascent_m:.0f} m",
                "roads": f"{alt.road_score:.0f}/100",
            }
            for alt in plan.alternatives
        ]
        st.dataframe(rows, hide_index=True, use_container_width=True)


def _render_plan(plan: RidePlan) -> None:
    st.header(f"{plan.route.name} from {plan.request.start.label.split(',')[0]}")
    st.caption(f"{plan.request.ride_date.strftime('%A %d %B %Y')} \N{MIDDLE DOT} {plan.bike_label}")

    for warning in plan.warnings:
        st.warning(warning, icon="\N{WARNING SIGN}")

    _render_summary(plan)

    left, right = st.columns([3, 2], gap="medium")
    with left:
        st_folium(
            build_map(plan),
            height=520,
            use_container_width=True,
            # Stops a pan or zoom from re-running the whole script.
            returned_objects=[],
            key=f"map_{plan.route.candidate_id}_{plan.request.ride_date}",
        )
    with right:
        if plan.briefing:
            st.subheader("Your briefing")
            st.write(plan.briefing)
        _render_fuel(plan)

    _render_weather_detail(plan)
    _render_gear(plan)
    _render_alternatives(plan)

    st.divider()
    cols = st.columns([1, 1, 4])
    if cols[0].button("Save this plan", type="secondary"):
        save_plan(
            SavedPlan(
                title=plan.route.name,
                ride_date=plan.request.ride_date,
                distance_km=plan.route.distance_km,
                payload=plan.model_dump_json(),
            )
        )
        st.success("Saved to history.")
    cols[1].download_button(
        "Download JSON",
        data=plan.model_dump_json(indent=2),
        file_name=f"ridewise-{plan.request.ride_date}-{plan.route.candidate_id}.json",
        mime="application/json",
    )


def page_plan(bike: Motorcycle | None) -> None:
    st.title("Plan a ride")
    ready = _setup_banner()

    if bike is None:
        st.info("Add a motorcycle in **Garage** first \N{EM DASH} the plan depends on it.")
        return

    profile = get_profile()

    with st.form("plan_form"):
        raw = st.text_area(
            "What kind of ride?",
            placeholder="Twisty backroads this Saturday, about 250 km, back before dark. "
            "Somewhere with a view for lunch.",
            help="Free text is optional. Anything you write here overrides the fields below.",
            height=80,
        )
        cols = st.columns([2, 1, 1])
        start_place = cols[0].text_input(
            "Start and finish", value=profile.home_label or "", placeholder="City or address"
        )
        distance = cols[1].number_input(
            "Distance (km)", min_value=20, max_value=1200, value=250, step=10
        )
        ride_date = cols[2].date_input(
            "Date",
            value=date.today(),
            min_value=date.today(),
            max_value=date.today() + timedelta(days=16),
        )

        cols = st.columns([1, 1, 1, 1])
        earliest = cols[0].time_input("Leave after", value=time(8, 0), step=1800)
        latest = cols[1].time_input("Home by", value=time(19, 0), step=1800)
        prefer_twisty = cols[2].checkbox("Prefer twisty roads", value=True)
        avoid_highways = cols[3].checkbox("Avoid motorways", value=True)

        submitted = st.form_submit_button(
            "Plan my ride", type="primary", disabled=not ready, use_container_width=True
        )

    if submitted:
        with st.status("Planning your ride\N{HORIZONTAL ELLIPSIS}", expanded=True) as status:
            plan: RidePlan | None = None
            try:
                for node, update in plan_ride_stream(
                    raw_request=raw,
                    bike=bike,
                    profile=profile,
                    start_place=start_place,
                    distance_km=float(distance),
                    ride_date=ride_date,
                    earliest=earliest.strftime("%H:%M"),
                    latest=latest.strftime("%H:%M"),
                    avoid_highways=avoid_highways,
                    prefer_twisty=prefer_twisty,
                ):
                    label = NODE_LABELS.get(node, node)
                    for line in update.get("progress", []):
                        st.write(f"**{label}** \N{EM DASH} {line}")
                    if "plan" in update:
                        plan = update["plan"]
            except PlannerFailure as exc:
                status.update(label="Could not plan this ride", state="error")
                st.error(str(exc))
                return
            except Exception as exc:  # pragma: no cover - surface anything unexpected
                status.update(label="Something went wrong", state="error")
                st.exception(exc)
                return
            status.update(label="Plan ready", state="complete", expanded=False)

        if plan is not None:
            st.session_state["plan"] = plan.model_dump_json()
            # Drop the previous ride's departure choice.
            st.session_state.pop("departure_choice", None)

    stored = st.session_state.get("plan")
    if stored:
        st.divider()
        _render_plan(RidePlan.model_validate_json(stored))


# ---------------------------------------------------------------------------
# garage page
# ---------------------------------------------------------------------------


def _bike_form(bike: Motorcycle | None, key: str) -> Motorcycle | None:
    """Shared add/edit form. Returns the bike to save, or None."""
    existing = bike or Motorcycle(
        nickname="", make="", model="", tank_liters=15.0, consumption_l_per_100km=5.0
    )

    with st.form(key):
        cols = st.columns([1, 1, 1, 1])
        nickname = cols[0].text_input("Nickname", value=existing.nickname)
        make = cols[1].text_input("Make", value=existing.make)
        model = cols[2].text_input("Model", value=existing.model)
        year = cols[3].number_input(
            "Year",
            min_value=1950,
            max_value=date.today().year + 1,
            value=existing.year or date.today().year,
        )

        cols = st.columns([1, 1, 1, 1])
        category = cols[0].selectbox(
            "Category",
            list(BikeCategory),
            index=list(BikeCategory).index(existing.category),
            format_func=lambda c: c.value,
        )
        tank = cols[1].number_input(
            "Tank (L)", min_value=1.0, max_value=60.0, value=float(existing.tank_liters), step=0.5
        )
        consumption = cols[2].number_input(
            "Consumption (L/100 km)",
            min_value=1.0,
            max_value=15.0,
            value=float(existing.consumption_l_per_100km),
            step=0.1,
        )
        reserve = cols[3].number_input(
            "Reserve kept (L)",
            min_value=0.0,
            max_value=10.0,
            value=float(existing.reserve_liters),
            step=0.5,
            help="Fuel you do not plan to use. Range is calculated without it.",
        )

        cols = st.columns([1, 1, 1, 1])
        wind = cols[0].selectbox(
            "Wind protection",
            list(WindProtection),
            index=list(WindProtection).index(existing.wind_protection),
            format_func=lambda w: w.value,
        )
        tires = cols[1].selectbox(
            "Tyres",
            list(TireType),
            index=list(TireType).index(existing.tire_type),
            format_func=lambda t: t.value,
        )
        grips = cols[2].checkbox("Heated grips", value=existing.heated_grips)
        luggage = cols[3].checkbox("Luggage fitted", value=existing.has_luggage)

        notes = st.text_area(
            "Notes",
            value=existing.notes,
            placeholder="Anything the planner should know: screen height, suspension, "
            "what it hates.",
            height=70,
        )
        is_default = st.checkbox("Use as my default bike", value=existing.is_default)

        usable = max(tank - reserve, 0.0)
        est_range = usable / consumption * 100 if consumption > 0 else 0
        st.caption(
            f"Usable range: **{est_range:.0f} km** ({usable:.1f} L of {tank:.1f} L "
            f"at {consumption:.1f} L/100 km)"
        )

        if st.form_submit_button("Save", type="primary"):
            if not (nickname and make and model):
                st.error("Nickname, make and model are all required.")
                return None
            existing.nickname = nickname
            existing.make = make
            existing.model = model
            existing.year = int(year)
            # selectbox is Optional-typed; the option list is never empty.
            existing.category = category or existing.category
            existing.tank_liters = float(tank)
            existing.consumption_l_per_100km = float(consumption)
            existing.reserve_liters = float(reserve)
            existing.wind_protection = wind or existing.wind_protection
            existing.tire_type = tires or existing.tire_type
            existing.heated_grips = grips
            existing.has_luggage = luggage
            existing.notes = notes
            existing.is_default = is_default
            return existing
    return None


def page_garage() -> None:
    st.title("Garage")
    st.caption("The planner reads these numbers: fuel for the stops, protection for the gear.")

    bikes = list_motorcycles()
    for bike in bikes:
        marker = " \N{BLACK STAR}" if bike.is_default else ""
        with st.expander(f"{bike.nickname}{marker} \N{MIDDLE DOT} {bike.label}"):
            st.caption(
                f"{bike.category.value} \N{MIDDLE DOT} {bike.range_km:.0f} km usable range "
                f"\N{MIDDLE DOT} {bike.wind_protection.value} wind protection "
                f"\N{MIDDLE DOT} {bike.tire_type.value} tyres"
            )
            updated = _bike_form(bike, key=f"edit_{bike.id}")
            if updated is not None:
                save_motorcycle(updated)
                st.success(f"Saved {updated.label}.")
                st.rerun()
            if st.button("Delete", key=f"del_{bike.id}"):
                delete_motorcycle(bike.id)  # type: ignore[arg-type]
                st.rerun()

    st.divider()
    with st.expander("Add a motorcycle", expanded=not bikes):
        new_bike = _bike_form(None, key="add_bike")
        if new_bike is not None:
            save_motorcycle(new_bike)
            st.success(f"Added {new_bike.label}.")
            st.rerun()


# ---------------------------------------------------------------------------
# profile page
# ---------------------------------------------------------------------------


def page_profile() -> None:
    st.title("Rider profile")
    profile = get_profile()

    with st.form("profile_form"):
        cols = st.columns([1, 2])
        name = cols[0].text_input("Name", value=profile.name)
        home = cols[1].text_input(
            "Home base", value=profile.home_label, placeholder="City, country"
        )

        cols = st.columns([1, 1, 1])
        experience = cols[0].selectbox(
            "Experience",
            list(Experience),
            index=list(Experience).index(profile.experience),
            format_func=lambda e: e.value,
        )
        min_temp = cols[1].number_input(
            "Coldest you will ride (\N{DEGREE SIGN}C)",
            min_value=-20.0,
            max_value=25.0,
            value=float(profile.min_comfortable_temp_c),
            step=1.0,
            help="Weather windows are penalised below this apparent temperature.",
        )
        accepts_rain = cols[2].checkbox("I do not mind rain", value=profile.accepts_rain)

        if st.form_submit_button("Save", type="primary"):
            profile.name = name
            profile.home_label = home
            profile.experience = experience or profile.experience
            profile.min_comfortable_temp_c = float(min_temp)
            profile.accepts_rain = accepts_rain
            save_profile(profile)
            st.success("Profile saved.")

    st.divider()
    st.subheader("Status")
    settings = get_settings()
    rows = [
        {
            "service": "OpenRouteService (routes, geocoding)",
            "status": "configured" if settings.ors_api_key else "missing key",
        },
        {"service": "Open-Meteo (forecast)", "status": "no key needed"},
        {"service": "Overpass / OpenStreetMap (fuel)", "status": "no key needed"},
        {"service": f"LLM via LiteLLM ({settings.llm_model})", "status": "set in .env"},
        {
            "service": "Langfuse (tracing)",
            "status": "enabled" if tracing_enabled() else "not configured",
        },
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# history page
# ---------------------------------------------------------------------------


def page_history() -> None:
    st.title("History")
    plans = list_plans()
    if not plans:
        st.info("No saved plans yet. Plan a ride and press **Save this plan**.")
        return

    for saved in plans:
        with st.expander(
            f"{saved.ride_date.strftime('%d %b %Y')} \N{MIDDLE DOT} {saved.title} "
            f"({saved.distance_km:.0f} km)"
        ):
            if st.button("Open", key=f"open_{saved.id}"):
                st.session_state["plan"] = saved.payload
                st.session_state["nav"] = "Plan a ride"
                st.rerun()
            plan = RidePlan.model_validate_json(saved.payload)
            if plan.briefing:
                st.write(plan.briefing)


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------


def main() -> None:
    bikes = list_motorcycles()

    with st.sidebar:
        st.title("\N{RACING MOTORCYCLE} RideWise")
        st.caption("Route, weather window, fuel and gear.")

        selected_bike: Motorcycle | None = None
        if bikes:
            selected_bike = st.selectbox(
                "Bike",
                bikes,
                format_func=lambda b: f"{b.nickname} ({b.label})",
                key="bike_choice",
            )
            if selected_bike:
                st.caption(
                    f"{selected_bike.range_km:.0f} km usable range \N{MIDDLE DOT} "
                    f"{selected_bike.tire_type.value} tyres"
                )

        st.divider()
        page = st.radio(
            "Go to",
            ["Plan a ride", "Garage", "Rider profile", "History"],
            key="nav",
            label_visibility="collapsed",
        )
        st.divider()
        if tracing_enabled():
            st.caption("Langfuse tracing on")

    if page == "Plan a ride":
        page_plan(selected_bike)
    elif page == "Garage":
        page_garage()
    elif page == "Rider profile":
        page_profile()
    else:
        page_history()


main()
