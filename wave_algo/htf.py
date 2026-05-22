"""Higher-timeframe regime inference and alignment filtering."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pandas as pd

from wave_algo.data import OHLCVSchemaError, load_ohlcv
from wave_algo.models import Direction, HTFState, Pivot, TradeSignal, normalize_direction
from wave_algo.pivots import ZigZagParams, detect_pivots
from wave_algo.rules import validate_impulse, validate_wave_1_to_2, validate_wave_1_to_4
from wave_algo.scoring import SCORE_WEIGHTS, htf_alignment_score

DEFAULT_ALIGNMENT_TIMEFRAME = "4h"
DEFAULT_DAILY_VETO_TIMEFRAMES = ("1d", "daily")


@dataclass(frozen=True)
class HTFTimeframeResult:
    """Diagnostic state for one optional higher timeframe."""

    timeframe: str | None
    state: HTFState
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
            "state": self.state.to_dict(),
            "error": self.error,
        }


@dataclass(frozen=True)
class HTFContext:
    """Per-symbol HTF diagnostics used by the signal filter."""

    symbol: str
    alignment: HTFTimeframeResult
    veto: HTFTimeframeResult
    timeframes: dict[str, HTFTimeframeResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "alignment": self.alignment.to_dict(),
            "veto": self.veto.to_dict(),
            "timeframes": {
                timeframe: result.to_dict()
                for timeframe, result in sorted(self.timeframes.items())
            },
        }


@dataclass(frozen=True)
class HTFSignalDecision:
    """Alignment decision for one generated signal."""

    signal: TradeSignal
    allowed: bool
    reason: str
    alignment_state: HTFState
    veto_state: HTFState

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.signal.symbol,
            "timeframe": self.signal.timeframe,
            "setup_type": self.signal.setup_type,
            "direction": self.signal.direction.value,
            "signal_time": _serialize_time(self.signal.signal_time),
            "confidence": self.signal.confidence,
            "allowed": self.allowed,
            "reason": self.reason,
            "alignment_state": self.alignment_state.to_dict(),
            "veto_state": self.veto_state.to_dict(),
        }


@dataclass(frozen=True)
class HTFFilterResult:
    """Allowed and blocked signals after HTF alignment/veto checks."""

    allowed_signals: tuple[TradeSignal, ...]
    blocked_signals: tuple[HTFSignalDecision, ...]
    decisions: tuple[HTFSignalDecision, ...]

    @property
    def allowed_count(self) -> int:
        return len(self.allowed_signals)

    @property
    def blocked_count(self) -> int:
        return len(self.blocked_signals)

    @property
    def block_reasons(self) -> dict[str, int]:
        return dict(Counter(decision.reason for decision in self.blocked_signals))


def infer_htf_state_from_pivots(
    pivots: Sequence[Pivot],
    timeframe: str | None = None,
) -> HTFState:
    """Infer bullish/bearish/neutral from latest validator-compatible pivot windows."""

    ordered = tuple(sorted(pivots, key=lambda pivot: pivot.index))
    if len(ordered) < 3:
        return HTFState(
            state="neutral",
            timeframe=timeframe,
            reason="fewer than three pivots for hard-rule validation",
        )

    diagnostics: list[str] = []
    for window_size, label, validator in (
        (6, "complete_impulse", validate_impulse),
        (5, "wave_1_to_4", validate_wave_1_to_4),
        (3, "wave_1_to_2", validate_wave_1_to_2),
    ):
        if len(ordered) < window_size:
            continue

        window = ordered[-window_size:]
        valid_directions: list[Direction] = []
        invalid_codes: dict[str, str] = {}
        for direction in (Direction.LONG, Direction.SHORT):
            result = validator(window, direction)
            if result.valid:
                valid_directions.append(direction)
            else:
                invalid_codes[direction.value] = _violation_codes(result.violations)

        if len(valid_directions) == 1:
            direction = valid_directions[0]
            return HTFState(
                state=_state_for_direction(direction),
                timeframe=timeframe,
                reason=(
                    f"latest {window_size}-pivot {label} validates as "
                    f"{direction.value}"
                ),
            )
        if len(valid_directions) > 1:
            return HTFState(
                state="neutral",
                timeframe=timeframe,
                reason=f"ambiguous {label} validation matched long and short",
            )

        diagnostics.append(
            f"{label} invalid "
            f"(long={invalid_codes['long']}; short={invalid_codes['short']})"
        )

    return HTFState(
        state="neutral",
        timeframe=timeframe,
        reason="; ".join(diagnostics),
    )


def infer_htf_state_from_ohlcv(
    df: pd.DataFrame,
    *,
    timeframe: str | None = None,
    pivot_params: ZigZagParams | None = None,
) -> HTFState:
    """Infer an HTF state directly from normalized OHLCV data."""

    pivots = detect_pivots(df, pivot_params or ZigZagParams())
    return infer_htf_state_from_pivots(pivots, timeframe=timeframe)


def analyze_htf_ohlcv(
    df: pd.DataFrame,
    *,
    timeframe: str,
    pivot_params: ZigZagParams | None = None,
) -> HTFTimeframeResult:
    """Return HTF state plus bounded diagnostics for one loaded timeframe."""

    frame = df.reset_index(drop=True).copy()
    params = pivot_params or ZigZagParams()
    pivots = detect_pivots(frame, params)
    return HTFTimeframeResult(
        timeframe=timeframe,
        state=infer_htf_state_from_pivots(pivots, timeframe=timeframe),
        available=True,
        rows=len(frame),
        pivot_count=len(pivots),
        frame=frame,
        pivot_params=params,
    )


def load_htf_context(
    symbol: str,
    data_dir: str | Path,
    *,
    alignment_timeframe: str = DEFAULT_ALIGNMENT_TIMEFRAME,
    veto_timeframes: Sequence[str] = DEFAULT_DAILY_VETO_TIMEFRAMES,
    pivot_params: ZigZagParams | None = None,
) -> HTFContext:
    """Load optional 4h/daily HTF data and infer the per-symbol filter context."""

    results: dict[str, HTFTimeframeResult] = {}
    alignment = _load_optional_htf(
        symbol,
        alignment_timeframe,
        data_dir,
        pivot_params=pivot_params,
    )
    results[alignment_timeframe] = alignment

    veto_candidates: list[HTFTimeframeResult] = []
    for timeframe in veto_timeframes:
        if timeframe in results:
            continue
        result = _load_optional_htf(
            symbol,
            timeframe,
            data_dir,
            pivot_params=pivot_params,
        )
        results[timeframe] = result
        veto_candidates.append(result)

    veto = next(
        (candidate for candidate in veto_candidates if candidate.available),
        _missing_result(
            ",".join(veto_timeframes) if veto_timeframes else None,
            "no daily veto data found",
            error=None,
        ),
    )
    return HTFContext(
        symbol=symbol,
        alignment=alignment,
        veto=veto,
        timeframes=results,
    )


def htf_allows_direction(direction: Direction | str, state: HTFState) -> bool:
    """Return whether an HTF state aligns with a signal direction."""

    normalized = normalize_direction(direction)
    return state.state == normalized.aligned_htf_state


def evaluate_signal_alignment(signal: TradeSignal, context: HTFContext) -> HTFSignalDecision:
    """Apply the required 4h alignment plus daily veto rule to one signal."""

    direction = normalize_direction(signal.direction)
    alignment = _result_asof_signal(context.alignment, signal.signal_time)
    veto = _result_asof_signal(context.veto, signal.signal_time)
    evaluated_signal = _signal_with_htf_state(signal, alignment.state)
    alignment_label = alignment.timeframe or DEFAULT_ALIGNMENT_TIMEFRAME

    if not alignment.available:
        return _decision(
            evaluated_signal,
            False,
            f"{alignment_label}_unavailable",
            alignment,
            veto,
        )
    if not htf_allows_direction(direction, alignment.state):
        return _decision(
            evaluated_signal,
            False,
            f"{alignment_label}_{alignment.state.state}_not_{direction.aligned_htf_state}",
            alignment,
            veto,
        )
    if direction is Direction.LONG and veto.state.state == "bearish":
        return _decision(evaluated_signal, False, "daily_bearish_veto", alignment, veto)
    if direction is Direction.SHORT and veto.state.state == "bullish":
        return _decision(evaluated_signal, False, "daily_bullish_veto", alignment, veto)

    return _decision(evaluated_signal, True, "allowed", alignment, veto)


def filter_signals_by_htf(
    signals: Sequence[TradeSignal],
    contexts: dict[str, HTFContext],
    *,
    alignment_timeframe: str = DEFAULT_ALIGNMENT_TIMEFRAME,
) -> HTFFilterResult:
    """Filter generated signals while preserving per-signal block diagnostics."""

    allowed: list[TradeSignal] = []
    blocked: list[HTFSignalDecision] = []
    decisions: list[HTFSignalDecision] = []
    for signal in signals:
        context = contexts.get(signal.symbol) or _missing_context(
            signal.symbol,
            alignment_timeframe,
        )
        decision = evaluate_signal_alignment(signal, context)
        decisions.append(decision)
        if decision.allowed:
            allowed.append(decision.signal)
        else:
            blocked.append(decision)

    return HTFFilterResult(
        allowed_signals=tuple(allowed),
        blocked_signals=tuple(blocked),
        decisions=tuple(decisions),
    )


def _load_optional_htf(
    symbol: str,
    timeframe: str,
    data_dir: str | Path,
    *,
    pivot_params: ZigZagParams | None,
) -> HTFTimeframeResult:
    try:
        frame = load_ohlcv(symbol, timeframe, data_dir)
    except FileNotFoundError as exc:
        return _missing_result(
            timeframe,
            f"{timeframe} OHLCV data unavailable",
            error=str(exc),
        )
    except (OHLCVSchemaError, ValueError) as exc:
        return _missing_result(
            timeframe,
            f"{timeframe} OHLCV data invalid",
            error=str(exc),
        )

    try:
        return analyze_htf_ohlcv(frame, timeframe=timeframe, pivot_params=pivot_params)
    except ValueError as exc:
        return _missing_result(
            timeframe,
            f"{timeframe} pivot detection failed",
            error=str(exc),
        )


def _missing_context(symbol: str, alignment_timeframe: str) -> HTFContext:
    alignment = _missing_result(
        alignment_timeframe,
        f"{alignment_timeframe} HTF context missing",
        error=None,
    )
    veto = _missing_result("daily", "daily veto context missing", error=None)
    return HTFContext(
        symbol=symbol,
        alignment=alignment,
        veto=veto,
        timeframes={alignment_timeframe: alignment, "daily": veto},
    )


def _missing_result(
    timeframe: str | None,
    reason: str,
    *,
    error: str | None,
) -> HTFTimeframeResult:
    return HTFTimeframeResult(
        timeframe=timeframe,
        state=HTFState(state="neutral", timeframe=timeframe, reason=reason),
        available=False,
        error=error,
    )


def _result_asof_signal(result: HTFTimeframeResult, signal_time: Any) -> HTFTimeframeResult:
    """Recompute a timeframe result using only bars completed by the signal time."""

    if not result.available or result.frame is None:
        return result

    frame = _completed_frame_asof(
        result.frame,
        timeframe=result.timeframe,
        signal_time=signal_time,
    )
    if frame.empty:
        timeframe = result.timeframe
        return HTFTimeframeResult(
            timeframe=timeframe,
            state=HTFState(
                state="neutral",
                timeframe=timeframe,
                reason=(
                    f"no completed {timeframe or 'HTF'} bars by signal time "
                    f"{_serialize_time(signal_time)}"
                ),
            ),
            available=True,
            rows=0,
            pivot_count=0,
            frame=frame,
            pivot_params=result.pivot_params,
        )

    return analyze_htf_ohlcv(
        frame,
        timeframe=result.timeframe or "htf",
        pivot_params=result.pivot_params,
    )


def _completed_frame_asof(
    frame: pd.DataFrame,
    *,
    timeframe: str | None,
    signal_time: Any,
) -> pd.DataFrame:
    signal_timestamp = pd.Timestamp(signal_time)
    bar_end_times = pd.to_datetime(frame["timestamp"]) + _timeframe_duration(timeframe)
    return frame.loc[bar_end_times <= signal_timestamp].reset_index(drop=True)


def _timeframe_duration(timeframe: str | None) -> pd.Timedelta:
    if timeframe is None:
        return pd.Timedelta(0)
    normalized = timeframe.strip().lower()
    if normalized == "daily":
        return pd.Timedelta(days=1)
    unit = normalized[-1:]
    amount_text = normalized[:-1] or "1"
    try:
        amount = float(amount_text)
    except ValueError:
        return pd.Timedelta(0)

    if unit == "h":
        return pd.Timedelta(hours=amount)
    if unit == "d":
        return pd.Timedelta(days=amount)
    if unit == "m":
        return pd.Timedelta(minutes=amount)
    return pd.Timedelta(0)


def _signal_with_htf_state(signal: TradeSignal, htf_state: HTFState) -> TradeSignal:
    score_breakdown = replace(
        signal.score_breakdown,
        htf_alignment=round(
            htf_alignment_score(signal.direction, htf_state) * SCORE_WEIGHTS["htf_alignment"],
            6,
        ),
    )
    return replace(
        signal,
        htf_state=htf_state,
        score_breakdown=score_breakdown,
        confidence=score_breakdown.total,
    )


def _decision(
    signal: TradeSignal,
    allowed: bool,
    reason: str,
    alignment: HTFTimeframeResult,
    veto: HTFTimeframeResult,
) -> HTFSignalDecision:
    return HTFSignalDecision(
        signal=signal,
        allowed=allowed,
        reason=reason,
        alignment_state=alignment.state,
        veto_state=veto.state,
    )


def _state_for_direction(direction: Direction) -> str:
    return "bullish" if direction is Direction.LONG else "bearish"


def _violation_codes(violations: Sequence[Any]) -> str:
    codes = [violation.code for violation in violations[:3]]
    if not codes:
        return "unknown"
    suffix = ",..." if len(violations) > 3 else ""
    return ",".join(codes) + suffix


def _serialize_time(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
