"""Command-line interface for the loaders package.

Usage:
    python -m loaders load <table_name>
    python -m loaders load --all
"""
import argparse

from loaders._config import TABLES
from loaders._db import load_to_table


def main() -> None:
    parser = argparse.ArgumentParser(prog="loaders")
    subparsers = parser.add_subparsers(dest="command", required=True)

    load_parser = subparsers.add_parser("load", help="load one or all tables")
    load_parser.add_argument(
        "name",
        nargs="?",
        choices=sorted(TABLES.keys()),
        help="which table to load (omit when using --all)",
    )
    load_parser.add_argument(
        "--all",
        action="store_true",
        help="load every table in the registry",
    )

    args = parser.parse_args()

    if args.command == "load":
        _run_load(args)


def _run_load(args: argparse.Namespace) -> None:
    if args.all and args.name:
        raise SystemExit("error: pass either a table name or --all, not both")
    if not args.all and not args.name:
        raise SystemExit("error: pass a table name or --all")

    targets = list(TABLES.keys()) if args.all else [args.name]
    for name in targets:
        print(f"=== loading {name} ===")
        load_to_table(TABLES[name])