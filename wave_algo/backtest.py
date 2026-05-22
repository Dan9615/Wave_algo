"""Thin backtest placeholders for Milestone 1.

Full next-open fill modeling, portfolio constraints, costs, partial exits, and
time stops are intentionally deferred until the signal engine has real-data tests.
"""

from __future__ import annotations

from collections.abc import Iterable

from wave_algo.models import TradeSignal


def filter_signals_by_confidence(
    signals: Iterable[TradeSignal],
    threshold: float = 70.0,
) -> list[TradeSignal]:
    """Return signals that pass the baseline confidence threshold."""

    return [signal for signal in signals if signal.confidence >= threshold]
