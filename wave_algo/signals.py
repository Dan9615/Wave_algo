"""Wave 3, Wave 5, and triangle signal calculators."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from wave_algo.fibonacci import (
    FIB_382,
    FIB_500,
    FIB_618,
    retracement_ratio,
    triangle_measured_target,
    triangle_measured_width,
    wave3_targets,
    wave5_targets,
)
from wave_algo.models import (
    Direction,
    HTFState,
    Pivot,
    PivotKind,
    SignalTarget,
    TradeSignal,
    normalize_direction,
)
from wave_algo.pivots import ZigZagParams, detect_pivots
from wave_algo.rules import validate_wave_1_to_2, validate_wave_1_to_4
from wave_algo.scoring import calculate_score, fib_fit_score, htf_alignment_score

DEFAULT_FIB_TOLERANCE = 0.08
DEFAULT_WAVE4_FIB_TOLERANCE = 0.12
PRICE_EPSILON = 1e-9


def _coerce_htf_state(htf_state: HTFState | str | None) -> HTFState:
    if htf_state is None:
        return HTFState()
    if isinstance(htf_state, HTFState):
        return htf_state
    return HTFState(state=htf_state, reason="provided as string")


def _soft_score(params: dict[str, Any], key: str, default: float = 0.5) -> float:
    soft_scores = params.get("soft_scores", {})
    return float(soft_scores.get(key, default))


def _targets_from_mapping(
    target_mapping: dict[str, float],
    *,
    size_fraction: float,
) -> tuple[SignalTarget, ...]:
    return tuple(
        SignalTarget(label=label, price=price, size_fraction=size_fraction)
        for label, price in target_mapping.items()
    )


def _confidence(
    *,
    fibonacci_fit: float,
    direction: Direction,
    htf_state: HTFState,
    params: dict[str, Any],
) -> tuple[float, Any]:
    breakdown = calculate_score(
        fibonacci_fit=fibonacci_fit,
        htf_alignment=htf_alignment_score(direction, htf_state),
        channel_fit=_soft_score(params, "channel_fit"),
        volume_confirmation=_soft_score(params, "volume_confirmation"),
        momentum_confirmation=_soft_score(params, "momentum_confirmation"),
        alternation_time=_soft_score(params, "alternation_time"),
    )
    return breakdown.total, breakdown


def calculate_wave3_signal(
    pivots: Sequence[Pivot],
    *,
    symbol: str,
    timeframe: str,
    direction: Direction | str,
    htf_state: HTFState | str | None = None,
    params: dict[str, Any] | None = None,
    signal_time: Any | None = None,
) -> TradeSignal | None:
    """Calculate a Wave 3 continuation signal from Wave 1 and Wave 2 pivots."""

    params = dict(params or {})
    normalized_direction = normalize_direction(direction)
    validation = validate_wave_1_to_2(pivots, normalized_direction)
    if not validation.valid:
        return None

    p0, p1, p2 = pivots
    ratio = retracement_ratio(p0.price, p1.price, p2.price, normalized_direction)
    fib_tolerance = float(params.get("fib_tolerance", DEFAULT_FIB_TOLERANCE))
    fibonacci_fit = fib_fit_score(ratio, (FIB_500, FIB_618), fib_tolerance)
    if fibonacci_fit <= 0:
        return None

    htf = _coerce_htf_state(htf_state)
    targets = _targets_from_mapping(
        wave3_targets(p0.price, p1.price, p2.price, normalized_direction),
        size_fraction=0.5,
    )
    confidence, breakdown = _confidence(
        fibonacci_fit=fibonacci_fit,
        direction=normalized_direction,
        htf_state=htf,
        params=params,
    )
    signal_params = {
        **params,
        "wave2_retracement_ratio": ratio,
        "accepted_retracements": [FIB_500, FIB_618],
        "fib_tolerance": fib_tolerance,
    }

    return TradeSignal(
        symbol=symbol,
        timeframe=timeframe,
        setup_type="wave_3",
        direction=normalized_direction,
        signal_time=signal_time if signal_time is not None else p2.time,
        entry=p2.price,
        stop=p0.price,
        targets=targets,
        confidence=confidence,
        score_breakdown=breakdown,
        htf_state=htf,
        invalidation=f"Wave 2 breaches Wave 1 start at {p0.price}",
        source_pivots=tuple(pivots),
        params=signal_params,
    )


def calculate_wave5_signal(
    pivots: Sequence[Pivot],
    *,
    symbol: str,
    timeframe: str,
    direction: Direction | str,
    htf_state: HTFState | str | None = None,
    params: dict[str, Any] | None = None,
    signal_time: Any | None = None,
) -> TradeSignal | None:
    """Calculate a Wave 5 continuation signal from Wave 1 through Wave 4 pivots."""

    params = dict(params or {})
    normalized_direction = normalize_direction(direction)
    validation = validate_wave_1_to_4(
        pivots,
        normalized_direction,
        allow_diagonal=bool(params.get("allow_diagonal", False)),
    )
    if not validation.valid:
        return None

    p0, p1, p2, p3, p4 = pivots
    ratio = retracement_ratio(p2.price, p3.price, p4.price, normalized_direction)
    fib_tolerance = float(params.get("fib_tolerance", DEFAULT_WAVE4_FIB_TOLERANCE))
    fibonacci_fit = fib_fit_score(ratio, (FIB_382,), fib_tolerance)
    if fibonacci_fit <= 0:
        return None

    htf = _coerce_htf_state(htf_state)
    targets = _targets_from_mapping(
        wave5_targets(p0.price, p1.price, p3.price, p4.price, normalized_direction),
        size_fraction=0.5,
    )
    confidence, breakdown = _confidence(
        fibonacci_fit=fibonacci_fit,
        direction=normalized_direction,
        htf_state=htf,
        params=params,
    )
    signal_params = {
        **params,
        "wave4_retracement_ratio": ratio,
        "accepted_retracements": [FIB_382],
        "fib_tolerance": fib_tolerance,
    }

    return TradeSignal(
        symbol=symbol,
        timeframe=timeframe,
        setup_type="wave_5",
        direction=normalized_direction,
        signal_time=signal_time if signal_time is not None else p4.time,
        entry=p4.price,
        stop=p1.price,
        targets=targets,
        confidence=confidence,
        score_breakdown=breakdown,
        htf_state=htf,
        invalidation=f"Wave 4 overlaps Wave 1 territory at {p1.price}",
        source_pivots=tuple(pivots),
        params=signal_params,
    )


def _triangle_mode(pivots: Sequence[Pivot]) -> str | None:
    highs = [pivot.price for pivot in pivots if pivot.kind is PivotKind.HIGH]
    lows = [pivot.price for pivot in pivots if pivot.kind is PivotKind.LOW]
    if len(highs) < 2 or len(lows) < 2:
        return None

    lower_highs = all(
        next_price < price for price, next_price in zip(highs, highs[1:], strict=False)
    )
    higher_lows = all(
        next_price > price for price, next_price in zip(lows, lows[1:], strict=False)
    )
    higher_highs = all(
        next_price > price for price, next_price in zip(highs, highs[1:], strict=False)
    )
    lower_lows = all(
        next_price < price for price, next_price in zip(lows, lows[1:], strict=False)
    )

    if lower_highs and higher_lows:
        return "contracting"
    if higher_highs and lower_lows:
        return "expanding"
    return None


def _has_alternating_kinds(pivots: Sequence[Pivot]) -> bool:
    return all(left.kind != right.kind for left, right in zip(pivots, pivots[1:], strict=False))


def _line_value_at(first: Pivot, last: Pivot, index: float) -> float:
    if first.index == last.index:
        return last.price
    slope = (last.price - first.price) / (last.index - first.index)
    return first.price + slope * (index - first.index)


def _triangle_breakout_level(
    pivots: Sequence[Pivot],
    direction: Direction,
    breakout_index: float,
) -> float | None:
    boundary_kind = PivotKind.HIGH if direction is Direction.LONG else PivotKind.LOW
    boundary = [pivot for pivot in pivots if pivot.kind is boundary_kind]
    if len(boundary) < 2:
        return None
    return _line_value_at(boundary[0], boundary[-1], breakout_index)


def calculate_triangle_signal(
    pivots: Sequence[Pivot],
    *,
    symbol: str,
    timeframe: str,
    direction: Direction | str,
    breakout_price: float,
    htf_state: HTFState | str | None = None,
    params: dict[str, Any] | None = None,
    signal_time: Any | None = None,
) -> TradeSignal | None:
    """Calculate a triangle breakout signal from a-b-c-d-e pivots."""

    params = dict(params or {})
    normalized_direction = normalize_direction(direction)
    if len(pivots) != 5 or not _has_alternating_kinds(pivots):
        return None

    mode = _triangle_mode(pivots)
    if mode is None:
        return None

    p_e = pivots[-1]
    if normalized_direction is Direction.LONG and p_e.price >= breakout_price:
        return None
    if normalized_direction is Direction.SHORT and p_e.price <= breakout_price:
        return None

    breakout_index = float(params.get("breakout_index", p_e.index + 1))
    breakout_level = _triangle_breakout_level(pivots, normalized_direction, breakout_index)
    if breakout_level is None:
        return None
    if (
        normalized_direction is Direction.LONG
        and breakout_price <= breakout_level + PRICE_EPSILON
    ):
        return None
    if (
        normalized_direction is Direction.SHORT
        and breakout_price >= breakout_level - PRICE_EPSILON
    ):
        return None

    htf = _coerce_htf_state(htf_state)
    target = triangle_measured_target(pivots, breakout_price, normalized_direction)
    width = triangle_measured_width(pivots)
    confidence, breakdown = _confidence(
        fibonacci_fit=1.0,
        direction=normalized_direction,
        htf_state=htf,
        params=params,
    )

    return TradeSignal(
        symbol=symbol,
        timeframe=timeframe,
        setup_type="triangle_breakout",
        direction=normalized_direction,
        signal_time=signal_time if signal_time is not None else p_e.time,
        entry=breakout_price,
        stop=p_e.price,
        targets=(SignalTarget(label="measured_move", price=target, size_fraction=1.0),),
        confidence=confidence,
        score_breakdown=breakdown,
        htf_state=htf,
        invalidation=f"Triangle breakout fails through wave e extreme at {p_e.price}",
        source_pivots=tuple(pivots),
        params={
            **params,
            "triangle_mode": mode,
            "measured_width": width,
            "breakout_index": breakout_index,
            "breakout_level": breakout_level,
        },
    )


def generate_signals_from_ohlcv(
    df: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    direction: Direction | str,
    htf_state: HTFState | str | None = None,
    pivot_params: ZigZagParams | None = None,
) -> list[TradeSignal]:
    """Detect pivots and return first-milestone candidate signals from the latest structure."""

    pivots = detect_pivots(df, pivot_params)
    signals: list[TradeSignal] = []
    if len(pivots) >= 3:
        wave3 = calculate_wave3_signal(
            pivots[-3:],
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            htf_state=htf_state,
        )
        if wave3 is not None:
            signals.append(wave3)
    if len(pivots) >= 5:
        wave5 = calculate_wave5_signal(
            pivots[-5:],
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            htf_state=htf_state,
        )
        if wave5 is not None:
            signals.append(wave5)
    return signals
