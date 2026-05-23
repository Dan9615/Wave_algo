"""Shared timeframe parsing and completed-bar slicing helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd


def timeframe_duration(timeframe: str | None) -> pd.Timedelta:
    """Return the duration represented by a compact timeframe label."""

    if timeframe is None:
        return pd.Timedelta(0)
    normalized = timeframe.strip().lower()
    if normalized in {"daily", "day"}:
        return pd.Timedelta(days=1)

    units = (
        ("minutes", "minutes"),
        ("minute", "minutes"),
        ("mins", "minutes"),
        ("min", "minutes"),
        ("m", "minutes"),
        ("hours", "hours"),
        ("hour", "hours"),
        ("hrs", "hours"),
        ("hr", "hours"),
        ("h", "hours"),
        ("days", "days"),
        ("day", "days"),
        ("d", "days"),
    )
    for suffix, unit in units:
        if not normalized.endswith(suffix):
            continue
        amount_text = normalized[: -len(suffix)] or "1"
        try:
            amount = float(amount_text)
        except ValueError:
            return pd.Timedelta(0)
        return pd.Timedelta(**{unit: amount})

    return pd.Timedelta(0)


def completed_frame_asof(
    frame: pd.DataFrame,
    *,
    timeframe: str | None,
    signal_time: Any,
) -> pd.DataFrame:
    """Return bars whose close/completion time is at or before ``signal_time``."""

    signal_timestamp = pd.Timestamp(signal_time)
    bar_end_times = pd.to_datetime(frame["timestamp"]) + timeframe_duration(timeframe)
    return frame.loc[bar_end_times <= signal_timestamp].reset_index(drop=True)


def serialize_time(value: Any) -> Any:
    """Return a JSON-friendly representation for timestamp-like values."""

    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
