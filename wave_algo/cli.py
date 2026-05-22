"""Command-line interface for local OHLCV signal generation and backtests."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from wave_algo.backtest import BacktestConfig, run_threshold_sensitivity
from wave_algo.data import OHLCVSchemaError, load_ohlcv
from wave_algo.pivots import ZigZagParams
from wave_algo.signals import generate_signals_from_ohlcv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wave-algo")
    parser.add_argument(
        "--version",
        action="version",
        version="wave-algo 0.1.0",
    )
    subparsers = parser.add_subparsers(dest="command")

    backtest = subparsers.add_parser("backtest", help="Run local Parquet OHLCV backtests.")
    backtest.add_argument("--data-dir", type=Path, default=Path("data/ohlcv"))
    backtest.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    backtest.add_argument("--timeframes", default="1h")
    backtest.add_argument("--thresholds", default="60,70,80")
    backtest.add_argument("--direction", choices=("long", "short", "both"), default="both")
    backtest.add_argument("--initial-equity", type=float, default=100_000.0)
    backtest.add_argument("--risk-fraction", type=float, default=0.01)
    backtest.add_argument("--fee-rate", type=float, default=0.0006)
    backtest.add_argument("--slippage-rate", type=float, default=0.0002)
    backtest.add_argument("--max-positions", type=int, default=3)
    backtest.add_argument("--reversal-pct", type=float, default=0.03)
    backtest.add_argument("--atr-period", type=int, default=14)
    backtest.add_argument("--atr-multiplier", type=float, default=0.0)
    backtest.add_argument("--min-bars-between-pivots", type=int, default=3)
    backtest.add_argument(
        "--include-trades",
        action="store_true",
        help="Include full trade/fill details in addition to summaries.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "backtest":
        try:
            report = _run_backtest_command(args)
        except (FileNotFoundError, OHLCVSchemaError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    parser.print_help()
    return 0


def _run_backtest_command(args: argparse.Namespace) -> dict[str, Any]:
    symbols = _parse_csv(args.symbols)
    timeframes = _parse_csv(args.timeframes)
    thresholds = [float(value) for value in _parse_csv(args.thresholds)]
    pivot_params = ZigZagParams(
        reversal_pct=args.reversal_pct,
        atr_period=args.atr_period,
        atr_multiplier=args.atr_multiplier,
        min_bars_between_pivots=args.min_bars_between_pivots,
    )
    config = BacktestConfig(
        initial_equity=args.initial_equity,
        risk_fraction=args.risk_fraction,
        fee_rate=args.fee_rate,
        slippage_rate=args.slippage_rate,
        max_positions=args.max_positions,
    )

    market_data = {}
    generated_signals = []
    for symbol in symbols:
        for timeframe in timeframes:
            frame = load_ohlcv(symbol, timeframe, args.data_dir)
            market_data[(symbol, timeframe)] = frame
            generated_signals.extend(
                generate_signals_from_ohlcv(
                    frame,
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=None if args.direction == "both" else args.direction,
                    htf_state="neutral",
                    pivot_params=pivot_params,
                )
            )

    results = run_threshold_sensitivity(
        market_data,
        generated_signals,
        thresholds=thresholds,
        config=config,
    )
    report: dict[str, Any] = {
        "data_dir": str(args.data_dir),
        "symbols": symbols,
        "timeframes": timeframes,
        "pivot_params": {
            "reversal_pct": pivot_params.reversal_pct,
            "atr_period": pivot_params.atr_period,
            "atr_multiplier": pivot_params.atr_multiplier,
            "min_bars_between_pivots": pivot_params.min_bars_between_pivots,
        },
        "signal_count": len(generated_signals),
        "signals_by_setup": dict(Counter(signal.setup_type for signal in generated_signals)),
        "thresholds": {
            _format_threshold(threshold): result.summary
            for threshold, result in results.items()
        },
    }
    if args.include_trades:
        report["results"] = {
            _format_threshold(threshold): result.to_dict()
            for threshold, result in results.items()
        }
    return report


def _parse_csv(value: str) -> list[str]:
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    if not parsed:
        raise ValueError("CSV option cannot be empty")
    return parsed


def _format_threshold(threshold: float) -> str:
    if threshold.is_integer():
        return str(int(threshold))
    return str(threshold)


if __name__ == "__main__":
    raise SystemExit(main())
