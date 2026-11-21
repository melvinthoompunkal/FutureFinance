"""Capture a local export, inspect the run log, or replay a publication offline."""

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3

import duckdb
import pandas as pd

from . import analytics as calc
from .archive import Archive
from .market_calendar import scheduled_window
from .scope import BENCHMARK, NEW_YORK, SECTORS

DATA = Path(__file__).resolve().parents[1] / "data"
REPLAY_FORMULA_VERSION = 1


def replay(archive: Archive, version: int, sector: str = "XLK", stock: str = "AAPL") -> dict:
    inputs, manifest = archive.load(version)
    day = pd.Timestamp(manifest["session"])
    split = inputs.prices("split_close")
    total = inputs.prices("total_return_close")
    dates = split.index[-6:]
    breadth = calc.breadth_history(inputs, split, dates)
    current = breadth[50][day].percent
    earlier = breadth[50][dates[0]].percent if len(dates) == 6 else None
    sector_row = calc.sector_ranking(total).loc[sector]
    stock_prices = split.get(stock, pd.Series(index=split.index, dtype=float))

    def number(value, digits: int = 6) -> float | None:
        return None if pd.isna(value) else round(float(value), digits)

    return {
        "version": version, "formula_version": REPLAY_FORMULA_VERSION,
        "session": manifest["session"], "vintage": manifest["vintage"],
        "market": {
            "spy_change_pct": number(calc.change(split[BENCHMARK], 1).loc[day]),
            "breadth": {
                window: {"above": item.above, "eligible": item.eligible, "expected": item.expected,
                         "percent": number(item.percent), "label": item.label}
                for window, readings in breadth.items() for item in [readings[day]]
            },
            "breadth_50_change_pp": number(current - earlier) if current is not None and earlier is not None else None,
        },
        "sector": {"symbol": sector, "change_20_pct": number(sector_row["Absolute, 20 sessions"]),
                   "vs_spy_20_pct": number(sector_row["20 sessions"])},
        "stock": {
            "symbol": stock,
            "change_pct": number(calc.change(stock_prices, 1).loc[day]),
            "vs_spy_20_pct": number(calc.change(calc.relative(total, stock), 20).loc[day]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DATA / "archive")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("capture", "tick"):
        capture = commands.add_parser(command)
        capture.add_argument("--input", type=Path, default=DATA / "inbox")
        if command == "capture":
            capture.add_argument("--session", required=True, type=date.fromisoformat)
    commands.add_parser("runs")
    inspect = commands.add_parser("replay")
    pick = inspect.add_mutually_exclusive_group(required=True)
    pick.add_argument("--session", type=date.fromisoformat)
    pick.add_argument("--version", type=int)
    inspect.add_argument("--sector", choices=SECTORS, default="XLK")
    inspect.add_argument("--stock", default="AAPL", type=str.upper)
    args = parser.parse_args()
    archive = Archive(args.archive)
    try:
        if args.command == "runs":
            result = archive.runs()
        elif args.command == "replay":
            version = args.version if args.version is not None else archive.published_sessions().get(args.session)
            if version is None:
                raise ValueError(f"No publication exists for {args.session}.")
            result = replay(archive, version, args.sector, args.stock)
        elif args.command == "tick":
            now = datetime.now(NEW_YORK)
            window = scheduled_window(now)
            if window is None:
                return 0
            result = archive.capture(args.input, now.date(), window, now=now, scheduled=True)
        else:
            result = archive.capture(args.input, args.session, "post-close")
    except (ValueError, OSError, duckdb.Error, sqlite3.Error) as error:
        parser.exit(1, f"{error}\n")
    if result is not None:
        print(json.dumps(result, indent=2, allow_nan=False))
    if args.command in ("capture", "tick") and result:
        return int(result["status"] == "failed" or (args.command == "capture" and result["status"] == "waiting"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
