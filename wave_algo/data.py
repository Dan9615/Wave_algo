"""Local OHLCV Parquet loading and schema normalization."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from wave_algo.pivots import REQUIRED_OHLC_COLUMNS

TIMESTAMP_COLUMN = "timestamp"
REQUIRED_OHLCV_COLUMNS = (TIMESTAMP_COLUMN, *REQUIRED_OHLC_COLUMNS)


class OHLCVSchemaError(ValueError):
    """Raised when local OHLCV data does not match the required contract."""


def ohlcv_path(symbol: str, timeframe: str, data_dir: str | Path = "data/ohlcv") -> Path:
    """Return the standard local OHLCV Parquet path for a symbol/timeframe pair."""

    return Path(data_dir) / f"{symbol}_{timeframe}.parquet"


def validate_ohlcv_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the required OHLCV columns.

    The returned frame is sorted by timestamp, reset to a dense integer index, and
    limited to the stable schema used by the signal and backtest layers.
    """

    missing = [column for column in REQUIRED_OHLCV_COLUMNS if column not in df.columns]
    if missing:
        raise OHLCVSchemaError(f"OHLCV data is missing required columns: {missing}")
    if df.empty:
        raise OHLCVSchemaError("OHLCV data cannot be empty")

    normalized = df.loc[:, REQUIRED_OHLCV_COLUMNS].copy()
    try:
        normalized[TIMESTAMP_COLUMN] = pd.to_datetime(normalized[TIMESTAMP_COLUMN])
    except Exception as exc:
        raise OHLCVSchemaError("OHLCV timestamp column must be datetime-like") from exc

    for column in REQUIRED_OHLC_COLUMNS:
        try:
            normalized[column] = pd.to_numeric(normalized[column], errors="raise").astype(float)
        except Exception as exc:
            raise OHLCVSchemaError(f"OHLCV column {column!r} must be numeric") from exc

    if normalized.isna().any().any():
        raise OHLCVSchemaError("OHLCV data cannot contain null values")

    return normalized.sort_values(TIMESTAMP_COLUMN).reset_index(drop=True)


def load_ohlcv(
    symbol: str,
    timeframe: str,
    data_dir: str | Path = "data/ohlcv",
) -> pd.DataFrame:
    """Load and normalize a local OHLCV Parquet file."""

    path = ohlcv_path(symbol, timeframe, data_dir)
    if not path.exists():
        raise FileNotFoundError(f"OHLCV parquet file not found: {path}")
    return validate_ohlcv_schema(pd.read_parquet(path, engine="pyarrow"))
