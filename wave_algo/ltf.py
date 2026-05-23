"""Lower-timeframe entry confirmation for generated Wave strategy signals."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from wave_algo.data import OHLCVSchemaError, load_ohlcv
from wave_algo.models import Direction, Pivot, TradeSignal, normalize_direction
from wave_algo.pivots import PivotConfirmation, ZigZagParams, detect_pivot_confirmations
from wave_algo.rules import validate_wave_1_to_2
from wave_algo.timeframes import completed_frame_asof, serialize_time, timeframe_duration

DEFAULT_CONFIRMATION_TIMEFRAME = "15m"
DEFAULT_CONFIRMATION_LOOKBACK_BARS = 16
PRICE_EPSILON = 1e-9


@dataclass(frozen=True)
class LTFTimeframeResult:
    """Diagnostic state for one optional lower-timeframe confirmation feed."""

    timeframe: str
    available: bool
    rows: int = 0
    pivot_count: int = 0
    error: str | None = None
    frame: pd.DataFrame | None = field(default=None, repr=False, compare=False)
    pivot_params: ZigZagParams | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "available": self.available,
            "rows": self.rows,
            "pivot_count": self.pivot_count,
            "error": self.error,
        }


@dataclass(frozen=True)
class LTFContext:
    """Per-symbol lower-timeframe data used by the confirmation filter."""

    symbol: str
    confirmation: LTFTimeframeResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "confirmation": self.confirmation.to_dict(),
        }


@dataclass(frozen=True)
class LTFSignalDecision:
    """Confirmation decision for one generated signal."""

    signal: TradeSignal
    allowed: bool
    reason: str
    confirmation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.signal.symbol,
            "timeframe": self.signal.timeframe,
            "setup_type": self.signal.setup_type,
            "direction": self.signal.direction.value,
            "signal_time": serialize_time(self.signal.signal_time),
            "confidence": self.signal.confidence,
            "allowed": self.allowed,
            "reason": self.reason,
            "confirmation": self.confirmation,
        }


@dataclass(frozen=True)
class LTFFilterResult:
    """Allowed and blocked signals after lower-timeframe confirmation."""

    allowed_signals: tuple[TradeSignal, ...]
    blocked_signals: tuple[LTFSignalDecision, ...]
    decisions: tuple[LTFSignalDecision, ...]

    @property
    def allowed_count(self) -> int:
        return len(self.allowed_signals)

    @property
    def blocked_count(self) -> int:
        return len(self.blocked_signals)

    @property
    def block_reasons(self) -> dict[str, int]:
        return dict(Counter(decision.reason for decision in self.blocked_signals))


def analyze_ltf_ohlcv(
    df: pd.DataFrame,
    *,
    timeframe: str,
    pivot_params: ZigZagParams | None = None,
) -> LTFTimeframeResult:
    """Return full-file lower-timeframe availability diagnostics."""

    frame = df.reset_index(drop=True).copy()
    params = pivot_params or ZigZagParams()
    confirmations = detect_pivot_confirmations(
        frame,
        params,
        include_unconfirmed_terminal=False,
    )
    return LTFTimeframeResult(
        timeframe=timeframe,
        available=True,
        rows=len(frame),
        pivot_count=len(confirmations),
        frame=frame,
        pivot_params=params,
    )


def load_ltf_context(
    symbol: str,
    data_dir: str | Path,
    *,
    confirmation_timeframe: str = DEFAULT_CONFIRMATION_TIMEFRAME,
    pivot_params: ZigZagParams | None = None,
) -> LTFContext:
    """Load optional lower-timeframe data without making unconfirmed runs fail."""

    try:
        frame = load_ohlcv(symbol, confirmation_timeframe, data_dir)
    except FileNotFoundError as exc:
        result = _missing_result(
            confirmation_timeframe,
            f"{confirmation_timeframe} OHLCV data unavailable",
            error=str(exc),
        )
    except (OHLCVSchemaError, ValueError) as exc:
        result = _missing_result(
            confirmation_timeframe,
            f"{confirmation_timeframe} OHLCV data invalid",
            error=str(exc),
        )
    else:
        try:
            result = analyze_ltf_ohlcv(
                frame,
                timeframe=confirmation_timeframe,
                pivot_params=pivot_params,
            )
        except ValueError as exc:
            result = _missing_result(
                confirmation_timeframe,
                f"{confirmation_timeframe} pivot detection failed",
                error=str(exc),
            )

    return LTFContext(symbol=symbol, confirmation=result)


def evaluate_signal_ltf_confirmation(
    signal: TradeSignal,
    context: LTFContext,
    *,
    lookback_bars: int = DEFAULT_CONFIRMATION_LOOKBACK_BARS,
) -> LTFSignalDecision:
    """Evaluate one signal against recent point-in-time lower-timeframe structure."""

    if lookback_bars <= 0:
        raise ValueError("lookback_bars must be positive")

    timeframe = context.confirmation.timeframe or DEFAULT_CONFIRMATION_TIMEFRAME
    base_confirmation = _base_confirmation_payload(
        signal,
        timeframe=timeframe,
        lookback_bars=lookback_bars,
    )
    if not context.confirmation.available or context.confirmation.frame is None:
        return LTFSignalDecision(
            signal=signal,
            allowed=False,
            reason=f"{timeframe}_unavailable",
            confirmation={
                **base_confirmation,
                "available": False,
                "error": context.confirmation.error,
            },
        )

    completed = completed_frame_asof(
        context.confirmation.frame,
        timeframe=timeframe,
        signal_time=base_confirmation["boundary_time"],
    )
    if completed.empty:
        return LTFSignalDecision(
            signal=signal,
            allowed=False,
            reason=f"{timeframe}_no_completed_bars",
            confirmation={
                **base_confirmation,
                "available": True,
                "completed_rows": 0,
                "pivot_count": 0,
            },
        )

    params = context.confirmation.pivot_params or ZigZagParams()
    confirmations = detect_pivot_confirmations(
        completed,
        params,
        include_unconfirmed_terminal=False,
    )
    direction = normalize_direction(signal.direction)
    matched = _find_recent_confirmation(
        completed,
        confirmations,
        direction,
        lookback_bars=lookback_bars,
    )
    diagnostic = {
        **base_confirmation,
        "available": True,
        "completed_rows": len(completed),
        "pivot_count": len(confirmations),
        "latest_close": float(completed.iloc[-1]["close"]),
        "direction": direction.value,
        "matched": matched,
    }
    if matched is None:
        label = "bullish" if direction is Direction.LONG else "bearish"
        reason = f"{timeframe}_no_{label}_confirmation"
        if len(confirmations) < 3 or _recent_window_count(
            confirmations,
            len(completed),
            lookback_bars,
        ) == 0:
            reason = f"{timeframe}_insufficient_recent_pivots"
        return LTFSignalDecision(
            signal=signal,
            allowed=False,
            reason=reason,
            confirmation=diagnostic,
        )

    return LTFSignalDecision(
        signal=signal,
        allowed=True,
        reason="allowed",
        confirmation=diagnostic,
    )


def filter_signals_by_ltf(
    signals: Sequence[TradeSignal],
    contexts: dict[str, LTFContext],
    *,
    confirmation_timeframe: str = DEFAULT_CONFIRMATION_TIMEFRAME,
    lookback_bars: int = DEFAULT_CONFIRMATION_LOOKBACK_BARS,
) -> LTFFilterResult:
    """Filter generated signals by recent lower-timeframe reversal confirmation."""

    if lookback_bars <= 0:
        raise ValueError("lookback_bars must be positive")

    allowed: list[TradeSignal] = []
    blocked: list[LTFSignalDecision] = []
    decisions: list[LTFSignalDecision] = []
    for signal in signals:
        context = contexts.get(signal.symbol) or _missing_context(
            signal.symbol,
            confirmation_timeframe,
        )
        decision = evaluate_signal_ltf_confirmation(
            signal,
            context,
            lookback_bars=lookback_bars,
        )
        decisions.append(decision)
        if decision.allowed:
            allowed.append(signal)
        else:
            blocked.append(decision)

    return LTFFilterResult(
        allowed_signals=tuple(allowed),
        blocked_signals=tuple(blocked),
        decisions=tuple(decisions),
    )


def _find_recent_confirmation(
    frame: pd.DataFrame,
    confirmations: Sequence[PivotConfirmation],
    direction: Direction,
    *,
    lookback_bars: int,
) -> dict[str, Any] | None:
    lookback_start_index = max(0, len(frame) - lookback_bars)
    latest_close = float(frame.iloc[-1]["close"])
    for start in range(len(confirmations) - 3, -1, -1):
        window_confirmations = confirmations[start : start + 3]
        if window_confirmations[-1].confirmation_index < lookback_start_index:
            break
        window = tuple(confirmation.pivot for confirmation in window_confirmations)
        validation = validate_wave_1_to_2(window, direction)
        if not validation.valid:
            continue
        if not _close_confirms_breakout(latest_close, window, direction):
            continue
        return _matched_payload(window_confirmations, latest_close, direction)
    return None


def _recent_window_count(
    confirmations: Sequence[PivotConfirmation],
    frame_rows: int,
    lookback_bars: int,
) -> int:
    lookback_start_index = max(0, frame_rows - lookback_bars)
    return sum(
        1
        for end in range(2, len(confirmations))
        if confirmations[end].confirmation_index >= lookback_start_index
    )


def _close_confirms_breakout(
    latest_close: float,
    pivots: Sequence[Pivot],
    direction: Direction,
) -> bool:
    impulse_extreme = pivots[1].price
    if direction is Direction.LONG:
        return latest_close > impulse_extreme + PRICE_EPSILON
    return latest_close < impulse_extreme - PRICE_EPSILON


def _matched_payload(
    confirmations: Sequence[PivotConfirmation],
    latest_close: float,
    direction: Direction,
) -> dict[str, Any]:
    latest_confirmation = max(confirmations, key=lambda item: item.confirmation_index)
    return {
        "direction": direction.value,
        "latest_close": latest_close,
        "confirmation_index": latest_confirmation.confirmation_index,
        "confirmation_time": serialize_time(latest_confirmation.confirmation_time),
        "pivots": [confirmation.pivot.to_dict() for confirmation in confirmations],
    }


def _base_confirmation_payload(
    signal: TradeSignal,
    *,
    timeframe: str,
    lookback_bars: int,
) -> dict[str, Any]:
    boundary_time = _signal_completion_boundary(signal)
    return {
        "timeframe": timeframe,
        "lookback_bars": lookback_bars,
        "base_timeframe": signal.timeframe,
        "signal_time": serialize_time(signal.signal_time),
        "boundary_time": serialize_time(boundary_time),
    }


def _signal_completion_boundary(signal: TradeSignal) -> pd.Timestamp:
    return pd.Timestamp(signal.signal_time) + timeframe_duration(signal.timeframe)


def _missing_context(symbol: str, timeframe: str) -> LTFContext:
    return LTFContext(
        symbol=symbol,
        confirmation=_missing_result(
            timeframe,
            f"{timeframe} LTF context missing for {symbol}",
            error=None,
        ),
    )


def _missing_result(timeframe: str, reason: str, *, error: str | None) -> LTFTimeframeResult:
    return LTFTimeframeResult(
        timeframe=timeframe,
        available=False,
        error=error or reason,
    )
