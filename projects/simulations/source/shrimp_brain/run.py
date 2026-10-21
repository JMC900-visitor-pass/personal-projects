"""Command-line runner for the synthetic Shrimp Brain simulator."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .data import DataSheet, OPEN_FIELD, SHELTER_FOOD, default_sheet_path
from .engine import SETTLE, ShrimpBrain, TrialResult


MODEL_CAVEAT = (
    "Synthetic heuristic simulation informed by recorded shrimp history. "
    "Outputs are not observed trajectories or scientifically validated predictions. "
    "Arena coordinates use arbitrary model units."
)


def _positive_radius(value: str) -> float:
    try:
        radius = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("radius must be a positive finite number") from exc
    if not math.isfinite(radius) or radius <= 0:
        raise argparse.ArgumentTypeError("radius must be a positive finite number")
    return radius


def _positive_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("count must be a positive integer") from exc
    if count < 1:
        raise argparse.ArgumentTypeError("count must be a positive integer")
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m shrimp_brain",
        description="Open a real-time cherry shrimp aquarium or run synthetic recorded trials.",
        epilog=(
            "Use --live for the interactive aquarium at normal clock speed. "
            "Batch trials produce 240 one-second ticks and 30 SETTLE dream ticks. "
            "These are heuristic outputs, not measurements."
        ),
    )
    parser.add_argument(
        "--data", type=Path, metavar="PATH",
        help="source CSV (default: locate raw.data.sheet.csv beside the repository)",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--list", action="store_true", help="list available shrimp and trials")
    selection.add_argument("--shrimp", "--id", metavar="ID", help="run this shrimp's recorded trials")
    selection.add_argument("--all", action="store_true", help="run every shrimp in the source CSV")
    parser.add_argument(
        "--trial", choices=sorted(OPEN_FIELD | SHELTER_FOOD),
        help="show/export only this trial type; earlier trials still establish carry-over state",
    )
    parser.add_argument("--seed", type=int, help="integer random seed for reproducible simulations")
    parser.add_argument("--live", action="store_true", help="watch and care for cherry shrimp in real time")
    parser.add_argument(
        "--tank", type=Path, metavar="PATH",
        help="live aquarium save file (default: ./shrimp_tank.json; requires --live)",
    )
    parser.add_argument(
        "--count", type=_positive_count, metavar="INT",
        help="founder shrimp when creating a live tank (default: 8; requires --live)",
    )
    parser.add_argument(
        "--radius", type=_positive_radius, default=10.0, metavar="FLOAT",
        help="arena radius in arbitrary model units (default: 10)",
    )
    parser.add_argument("--output", type=Path, metavar="PATH", help="write full simulation results as JSON")
    parser.add_argument("--csv", type=Path, metavar="PATH", help="write simulation and dream ticks as CSV")
    return parser


def _format_metric(value: float | None) -> str:
    return "NA" if value is None else f"{value:.3f}"


def _print_summary(result: TrialResult) -> None:
    trial = result.trial
    food = f", food found: {'yes' if result.food_found else 'no'}" if trial.is_shelter_food else ""
    print(
        f"{trial.id} / {trial.trial} / {trial.date} {trial.time}: "
        f"{len(result.ticks)} ticks, {len(result.dream)} dream ticks{food}"
    )
    metrics = (
        ("time_arena", "tl_arena", "frz_arena", "shelter_duration", "food_latency2")
        if trial.is_shelter_food
        else ("tracklength", "wall_dist", "area", "oft_tot_frz")
    )
    print("  " + ", ".join(f"{name}={_format_metric(getattr(result.summary, name))}" for name in metrics))


def _write_json(path: Path, results: list[TrialResult], args: argparse.Namespace, source: Path) -> None:
    payload = {
        "model_caveat": MODEL_CAVEAT,
        "source": str(source.resolve()),
        "seed": args.seed,
        "arena_radius": args.radius,
        "coordinate_units": "arbitrary model units",
        "tick_seconds": 1,
        "results": [result.as_dict() for result in results],
    }
    # Serialize before opening the destination, so invalid data cannot truncate it.
    serialized = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    path.write_text(serialized, encoding="utf-8")


def _write_csv(path: Path, results: list[TrialResult]) -> None:
    fields = [
        "id", "trial", "date", "time", "set_up", "order", "synthetic", "phase",
        "t", "x", "y", "speed", "state", "wall_dist", "in_arena", "food_found", "startle",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            trial = result.trial
            metadata = {
                "id": trial.id, "trial": trial.trial, "date": trial.date, "time": trial.time,
                "set_up": trial.set_up, "order": trial.order, "synthetic": True,
            }
            for tick in result.ticks:
                row = {**metadata, "phase": "trial", **asdict(tick)}
                writer.writerow({name: "NA" if row.get(name) is None else row[name] for name in fields})
            for tick in result.dream:
                row = {**metadata, "phase": "dream", **asdict(tick), "state": SETTLE}
                writer.writerow({name: "NA" if row.get(name) is None else row[name] for name in fields})


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.live and (args.tank is not None or args.count is not None):
        parser.error("--tank and --count require --live")
    args.tank = args.tank if args.tank is not None else Path.cwd() / "shrimp_tank.json"
    args.count = args.count if args.count is not None else 8
    if args.live and (args.trial or args.output or args.csv or args.all or args.list or args.shrimp):
        parser.error("--live cannot be combined with --trial, --output, --csv, --all, --list, or --shrimp")
    if args.list and (args.trial or args.output or args.csv):
        parser.error("--list cannot be combined with --trial, --output, or --csv")

    try:
        source = args.data if args.data is not None else Path(default_sheet_path())
        destinations = [path.resolve() for path in (args.output, args.csv) if path is not None]
        if source.resolve() in destinations:
            parser.error("output paths must differ from the source CSV")
        if args.live and source.resolve() == args.tank.resolve():
            parser.error("the tank save path must differ from the source CSV")
        if len(destinations) != len(set(destinations)):
            parser.error("--output and --csv must use different paths")
        sheet = DataSheet(source)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        parser.error(f"could not load data: {exc}; use --data PATH to select a source CSV")

    ids = sheet.shrimp_ids()
    if not ids:
        parser.error("the source CSV contains no shrimp trials")
    if args.live:
        try:
            from .aquarium import launch
            launch(sheet, seed=args.seed, count=args.count, save_path=args.tank)
        except (OSError, ValueError, RuntimeError, ImportError) as exc:
            parser.error(f"could not open aquarium: {exc}")
        return 0
    if args.list:
        for shrimp_id in ids:
            trials = sheet.shrimp[shrimp_id].trials_sorted()
            print(f"{shrimp_id}: {len(trials)} trials ({', '.join(trial.trial for trial in trials)})")
        return 0

    if args.shrimp is not None and args.shrimp not in sheet:
        parser.error(f"unknown shrimp ID {args.shrimp!r}; use --list to see available IDs")
    selected = ids if args.all else [args.shrimp if args.shrimp is not None else ids[0]]
    if args.trial:
        selected = [
            shrimp_id for shrimp_id in selected
            if any(trial.trial == args.trial for trial in sheet.shrimp[shrimp_id].trials)
        ]
        if not selected:
            parser.error(f"no {args.trial} trial for the selected shrimp; use --list to see available trials")

    print(MODEL_CAVEAT)
    if not args.all and args.shrimp is None:
        print(f"Selected first shrimp: {selected[0]} (use --shrimp ID or --all to change selection).")
    results: list[TrialResult] = []
    try:
        for shrimp_id in selected:
            brain = ShrimpBrain(sheet.shrimp[shrimp_id], seed=args.seed, arena_radius=args.radius)
            results.extend(result for result in brain.run_all() if args.trial is None or result.trial.trial == args.trial)
        for result in results:
            _print_summary(result)
        if args.output is not None:
            _write_json(args.output, results, args, source)
            print(f"JSON saved to {args.output}")
        if args.csv is not None:
            _write_csv(args.csv, results)
            print(f"CSV saved to {args.csv}")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
