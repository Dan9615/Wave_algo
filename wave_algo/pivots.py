"""Deterministic pivot detection using ZigZag reversal, ATR, and distance filters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from wave_algo.models import Pivot, PivotKind

REQUIRED_OHLC_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class ZigZagParams:
    """Configuration for deterministic swing-pivot detection."""

    reversal_pct: float = 0.03
    atr_period: int = 14
    atr_multiplier: float = 0.0
    min_bars_between_pivots: int = 3
    timestamp_column: str = "timestamp"

    def __post_init__(self) -> None:
        if self.reversal_pct <= 0:
            raise ValueError("reversal_pct must be positive")
        if self.atr_period <= 0:
            raise ValueError("atr_period must be positive")
        if self.atr_multiplier < 0:
            raise ValueError("atr_multiplier cannot be negative")
        if self.min_bars_between_pivots < 0:
            raise ValueError("min_bars_between_pivots cannot be negative")


@dataclass(frozen=True)
class PivotConfirmation:
    """A pivot plus the bar where that pivot became knowable."""

    pivot: Pivot
    confirmation_index: int
    confirmation_time: Any
    confirmed: bool = True


def validate_ohlcv(df: pd.DataFrame, timestamp_column: str | None = "timestamp") -> None:
    """Validate the OHLCV schema expected by the first-milestone engine."""

    required_columns = list(REQUIRED_OHLC_COLUMNS)
    if timestamp_column is not None:
        required_columns.append(timestamp_column)
    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]
    if missing:
        raise ValueError(f"OHLCV data is missing required columns: {missing}")
    if df.empty:
        raise ValueError("OHLCV data cannot be empty")


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range from OHLCV data."""

    validate_ohlcv(df, timestamp_column=None)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period, min_periods=1).mean()


def _threshold(price: float, atr: float, params: ZigZagParams) -> float:
    pct_threshold = abs(price) * params.reversal_pct
    atr_threshold = atr * params.atr_multiplier
    return max(pct_threshold, atr_threshold)


def _row_time(df: pd.DataFrame, index: int, timestamp_column: str) -> Any:
    return df.iloc[index][timestamp_column]


def _make_pivot(
    df: pd.DataFrame,
    index: int,
    price: float,
    kind: PivotKind,
    atr: float,
    params: ZigZagParams,
) -> Pivot:
    return Pivot(
        index=int(index),
        time=_row_time(df, int(index), params.timestamp_column),
        price=float(price),
        kind=kind,
        atr=float(atr),
    )


def _make_confirmation(
    df: pd.DataFrame,
    index: int,
    price: float,
    kind: PivotKind,
    atr: float,
    params: ZigZagParams,
    *,
    confirmation_index: int,
    confirmed: bool = True,
) -> PivotConfirmation:
    return PivotConfirmation(
        pivot=_make_pivot(df, index, price, kind, atr, params),
        confirmation_index=int(confirmation_index),
        confirmation_time=_row_time(df, int(confirmation_index), params.timestamp_column),
        confirmed=confirmed,
    )


def _append_confirmation(
    confirmations: list[PivotConfirmation],
    confirmation: PivotConfirmation,
) -> None:
    if not confirmations:
        confirmations.append(confirmation)
        return

    previous = confirmations[-1].pivot
    pivot = confirmation.pivot
    if previous.kind != pivot.kind:
        confirmations.append(confirmation)
        return

    if pivot.kind is PivotKind.HIGH and pivot.price > previous.price:
        confirmations[-1] = confirmation
    if pivot.kind is PivotKind.LOW and pivot.price < previous.price:
        confirmations[-1] = confirmation


def _passes_filters(
    previous_index: int | None,
    candidate_index: int,
    current_index: int,
    reversal_distance: float,
    threshold: float,
    params: ZigZagParams,
) -> bool:
    if (
        previous_index is not None
        and candidate_index - previous_index < params.min_bars_between_pivots
    ):
        return False
    if current_index - candidate_index < params.min_bars_between_pivots:
        return False
    return reversal_distance >= threshold


def _passes_final_distance(
    previous_index: int | None,
    candidate_index: int,
    params: ZigZagParams,
) -> bool:
    if previous_index is None:
        return True
    return candidate_index - previous_index >= params.min_bars_between_pivots


def detect_pivot_confirmations(
    df: pd.DataFrame,
    params: ZigZagParams | None = None,
    *,
    include_unconfirmed_terminal: bool = True,
) -> list[PivotConfirmation]:
    """Detect ZigZag pivots with the bar where each pivot became knowable.

    The algorithm confirms a swing only after price reverses by the larger of the
    configured percentage threshold and ATR threshold, with a minimum bar distance
    between the swing extreme and both adjacent confirmation points. The optional
    terminal pivot preserves the historical full-frame ZigZag view, but is marked
    as unconfirmed because no later reversal bar confirmed it.
    """

    params = params or ZigZagParams()
    validate_ohlcv(df, params.timestamp_column)
    if len(df) < 2:
        return []

    data = df.reset_index(drop=True).copy()
    atr = calculate_atr(data, params.atr_period).to_numpy(dtype=float)
    highs = data["high"].astype(float).to_numpy()
    lows = data["low"].astype(float).to_numpy()

    confirmations: list[PivotConfirmation] = []
    trend: str | None = None
    highest_index = lowest_index = 0
    highest_price = float(highs[0])
    lowest_price = float(lows[0])
    previous_pivot_index: int | None = None

    for index in range(1, len(data)):
        high = float(highs[index])
        low = float(lows[index])

        if high > highest_price:
            highest_index = index
            highest_price = high
        if low < lowest_price:
            lowest_index = index
            lowest_price = low

        if trend is None:
            up_distance = highest_price - lowest_price
            up_threshold = _threshold(lowest_price, float(atr[index]), params)
            down_threshold = _threshold(highest_price, float(atr[index]), params)
            if _passes_filters(
                None,
                lowest_index,
                highest_index,
                up_distance,
                up_threshold,
                params,
            ):
                _append_confirmation(
                    confirmations,
                    _make_confirmation(
                        data,
                        lowest_index,
                        lowest_price,
                        PivotKind.LOW,
                        atr[lowest_index],
                        params,
                        confirmation_index=highest_index,
                    ),
                )
                trend = "up"
                previous_pivot_index = lowest_index
            elif _passes_filters(
                None,
                highest_index,
                lowest_index,
                up_distance,
                down_threshold,
                params,
            ):
                _append_confirmation(
                    confirmations,
                    _make_confirmation(
                        data,
                        highest_index,
                        highest_price,
                        PivotKind.HIGH,
                        atr[highest_index],
                        params,
                        confirmation_index=lowest_index,
                    ),
                )
                trend = "down"
                previous_pivot_index = highest_index
            continue

        if trend == "up":
            if high > highest_price:
                highest_index = index
                highest_price = high
            reversal_distance = highest_price - low
            threshold = _threshold(highest_price, float(atr[index]), params)
            if _passes_filters(
                previous_pivot_index,
                highest_index,
                index,
                reversal_distance,
                threshold,
                params,
            ):
                _append_confirmation(
                    confirmations,
                    _make_confirmation(
                        data,
                        highest_index,
                        highest_price,
                        PivotKind.HIGH,
                        atr[highest_index],
                        params,
                        confirmation_index=index,
                    ),
                )
                trend = "down"
                previous_pivot_index = highest_index
                lowest_index = index
                lowest_price = low
        else:
            if low < lowest_price:
                lowest_index = index
                lowest_price = low
            reversal_distance = high - lowest_price
            threshold = _threshold(lowest_price, float(atr[index]), params)
            if _passes_filters(
                previous_pivot_index,
                lowest_index,
                index,
                reversal_distance,
                threshold,
                params,
            ):
                _append_confirmation(
                    confirmations,
                    _make_confirmation(
                        data,
                        lowest_index,
                        lowest_price,
                        PivotKind.LOW,
                        atr[lowest_index],
                        params,
                        confirmation_index=index,
                    ),
                )
                trend = "up"
                previous_pivot_index = lowest_index
                highest_index = index
                highest_price = high

    if (
        include_unconfirmed_terminal
        and trend == "up"
        and (not confirmations or confirmations[-1].pivot.index != highest_index)
        and _passes_final_distance(previous_pivot_index, highest_index, params)
    ):
        _append_confirmation(
            confirmations,
            _make_confirmation(
                data,
                highest_index,
                highest_price,
                PivotKind.HIGH,
                atr[highest_index],
                params,
                confirmation_index=len(data) - 1,
                confirmed=False,
            ),
        )
    if (
        include_unconfirmed_terminal
        and trend == "down"
        and (not confirmations or confirmations[-1].pivot.index != lowest_index)
        and _passes_final_distance(previous_pivot_index, lowest_index, params)
    ):
        _append_confirmation(
            confirmations,
            _make_confirmation(
                data,
                lowest_index,
                lowest_price,
                PivotKind.LOW,
                atr[lowest_index],
                params,
                confirmation_index=len(data) - 1,
                confirmed=False,
            ),
        )

    return [
        confirmation
        for confirmation in confirmations
        if np.isfinite(confirmation.pivot.price)
    ]


def detect_pivots(
    df: pd.DataFrame,
    params: ZigZagParams | None = None,
    *,
    include_unconfirmed_terminal: bool = True,
) -> list[Pivot]:
    """Detect deterministic ZigZag pivots from OHLCV data."""

    return [
        confirmation.pivot
        for confirmation in detect_pivot_confirmations(
            df,
            params,
            include_unconfirmed_terminal=include_unconfirmed_terminal,
        )
    ]
