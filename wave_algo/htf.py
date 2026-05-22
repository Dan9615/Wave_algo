"""Thin higher-timeframe state helpers for the first milestone."""

from __future__ import annotations

from collections.abc import Sequence

from wave_algo.models import Direction, HTFState, Pivot, normalize_direction


def infer_htf_state_from_pivots(pivots: Sequence[Pivot], timeframe: str | None = None) -> HTFState:
    """Infer a coarse bullish/bearish/neutral regime from pivot endpoints."""

    if len(pivots) < 2:
        return HTFState(state="neutral", timeframe=timeframe, reason="fewer than two pivots")
    first = pivots[0].price
    last = pivots[-1].price
    if last > first:
        return HTFState(
            state="bullish",
            timeframe=timeframe,
            reason="latest pivot above first pivot",
        )
    if last < first:
        return HTFState(
            state="bearish",
            timeframe=timeframe,
            reason="latest pivot below first pivot",
        )
    return HTFState(state="neutral", timeframe=timeframe, reason="flat pivot endpoints")


def htf_allows_direction(direction: Direction | str, state: HTFState) -> bool:
    """Return whether an HTF state aligns with a signal direction."""

    normalized = normalize_direction(direction)
    return state.state == normalized.aligned_htf_state
