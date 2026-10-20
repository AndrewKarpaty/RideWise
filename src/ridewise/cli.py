"""Command-line planner - handy for exercising the graph without the UI."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from ridewise.agent.graph import NODE_LABELS, plan_ride_stream
from ridewise.agent.nodes import PlannerFailure
from ridewise.db import list_motorcycles
from ridewise.models import Motorcycle, RidePlan
from ridewise.providers.weather import describe_code


def _pick_bike(nickname: str | None) -> Motorcycle | None:
    bikes = list_motorcycles()
    if not bikes:
        return None
    if not nickname:
        return bikes[0]
    for bike in bikes:
        if bike.nickname.lower() == nickname.lower():
            return bike
    names = ", ".join(b.nickname for b in bikes)
    raise SystemExit(f"No bike called {nickname!r}. Your garage has: {names}")


def _print_plan(plan: RidePlan) -> None:
    route, weather = plan.route, plan.weather
    rule = "-" * 72

    print(f"\n{rule}")
    print(f"{route.name} from {plan.request.start.label}")
    print(f"{plan.request.ride_date:%A %d %B %Y} | {plan.bike_label}")
    print(rule)

    print(
        f"{route.distance_km:.0f} km | {route.moving_duration_h:.1f} h moving | "
        f"{route.twistiness:.0f} deg/km | {route.ascent_m:.0f} m climb | "
        f"roads {route.road_score:.0f}/100"
    )

    if weather:
        print(
            f"\nDepart {weather.departure:%H:%M}, back {weather.arrival:%H:%M} "
            f"- {weather.score:.0f}/100"
        )
        print(f"  {weather.verdict}")
        for leg in weather.legs:
            hour = leg.weather
            print(
                f"  km {leg.distance_along_km:>4.0f} at {leg.eta:%H:%M}  "
                f"{describe_code(hour.weather_code):<18} "
                f"{hour.temperature_c:>4.0f}C (feels {hour.apparent_temperature_c:>4.0f}C)  "
                f"rain {hour.precipitation_probability:>3.0f}%  "
                f"gusts {hour.wind_gusts_kmh:>3.0f} km/h"
            )
    else:
        print("\nNo forecast available for this date.")

    print("\nFuel")
    if plan.fuel_stops:
        for stop in plan.fuel_stops:
            print(f"  km {stop.distance_along_km:>4.0f}  {stop.name} - {stop.reason}")
    else:
        print("  No stop needed on one tank.")

    if plan.gear:
        print("\nGear")
        for item in plan.gear:
            mark = "!" if item.essential else "-"
            print(f"  {mark} {item.item}: {item.reason}")

    if plan.briefing:
        print(f"\nBriefing\n  {plan.briefing}")

    if plan.warnings:
        print("\nWarnings")
        for warning in plan.warnings:
            print(f"  ! {warning}")
    print(f"{rule}\n")


def _cmd_plan(args: argparse.Namespace) -> int:
    bike = _pick_bike(args.bike)
    if bike is None:
        print(
            "Your garage is empty. Run `ridewise seed` for a starter bike, or add one in the app.",
            file=sys.stderr,
        )
        return 1

    ride_date = date.today()
    if args.date:
        try:
            ride_date = date.fromisoformat(args.date)
        except ValueError:
            raise SystemExit(f"--date must be YYYY-MM-DD, got {args.date!r}") from None

    plan: RidePlan | None = None
    try:
        for node, update in plan_ride_stream(
            raw_request=" ".join(args.request),
            bike=bike,
            start_place=args.start,
            distance_km=args.km,
            ride_date=ride_date,
            earliest=args.earliest,
            latest=args.latest,
            avoid_highways=not args.allow_highways,
            prefer_twisty=not args.no_twisty,
        ):
            for line in update.get("progress", []):
                print(f"  [{NODE_LABELS.get(node, node)}] {line}", file=sys.stderr)
            if "plan" in update:
                plan = update["plan"]
    except PlannerFailure as exc:
        print(f"\nCould not plan this ride: {exc}", file=sys.stderr)
        return 1

    if plan is None:
        print("\nThe planner produced no plan.", file=sys.stderr)
        return 1

    if args.json:
        print(plan.model_dump_json(indent=2))
    else:
        _print_plan(plan)
    return 0


def _cmd_garage(_: argparse.Namespace) -> int:
    bikes = list_motorcycles()
    if not bikes:
        print("Garage is empty. Run `ridewise seed`.")
        return 0
    for bike in bikes:
        star = " *" if bike.is_default else "  "
        print(
            f"{star} {bike.nickname:<16} {bike.label:<34} "
            f"{bike.range_km:>4.0f} km range  {bike.tire_type.value}"
        )
    return 0


def _cmd_seed(_: argparse.Namespace) -> int:
    from ridewise.seed import seed

    seed()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ridewise", description="AI ride planner for motorcyclists."
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log provider calls")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="plan a ride")
    plan.add_argument("request", nargs="*", help="free-text request, e.g. 'twisty 250 km Saturday'")
    plan.add_argument("--from", dest="start", default="", help="start and finish place")
    plan.add_argument("--km", type=float, default=250, help="target loop distance (default 250)")
    plan.add_argument("--date", help="ride date, YYYY-MM-DD (default today)")
    plan.add_argument("--bike", help="bike nickname (default: your default bike)")
    plan.add_argument("--earliest", default="08:00", help="earliest departure (default 08:00)")
    plan.add_argument("--latest", default="19:00", help="latest return (default 19:00)")
    plan.add_argument("--allow-highways", action="store_true", help="do not avoid motorways")
    plan.add_argument("--no-twisty", action="store_true", help="do not favour twisty roads")
    plan.add_argument("--json", action="store_true", help="print the plan as JSON")
    plan.set_defaults(func=_cmd_plan)

    sub.add_parser("garage", help="list your motorcycles").set_defaults(func=_cmd_garage)
    sub.add_parser("seed", help="add starter bikes and a home base").set_defaults(func=_cmd_seed)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
