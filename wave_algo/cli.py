"""Minimal CLI entry point for the first milestone."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wave-algo")
    parser.add_argument(
        "--version",
        action="version",
        version="wave-algo 0.1.0",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("signals",),
        help="Placeholder command; real-data loading arrives in a later milestone.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "signals":
        parser.error("real-data parquet signal loading is deferred beyond Milestone 1")
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
