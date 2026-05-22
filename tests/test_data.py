from pathlib import Path

import pandas as pd
import pytest

from wave_algo.data import OHLCVSchemaError, load_ohlcv, ohlcv_path, validate_ohlcv_schema


def ohlcv_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=3, freq="h"),
            "open": [100, 101, 102],
            "high": [101, 102, 103],
            "low": [99, 100, 101],
            "close": [100.5, 101.5, 102.5],
            "volume": [1000, 1100, 1200],
        }
    )


def test_ohlcv_path_uses_standard_filename() -> None:
    assert ohlcv_path("BTCUSDT", "1h", Path("data/ohlcv")) == Path(
        "data/ohlcv/BTCUSDT_1h.parquet"
    )


def test_load_ohlcv_reads_parquet_and_normalizes_schema(tmp_path: Path) -> None:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    frame = ohlcv_frame().sample(frac=1.0, random_state=1)
    frame.to_parquet(data_dir / "BTCUSDT_1h.parquet", engine="pyarrow")

    loaded = load_ohlcv("BTCUSDT", "1h", data_dir)

    assert list(loaded.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert loaded["timestamp"].is_monotonic_increasing
    assert loaded["open"].dtype == "float64"


def test_load_ohlcv_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="OHLCV parquet file not found"):
        load_ohlcv("ETHUSDT", "1h", tmp_path)


def test_validate_ohlcv_schema_rejects_missing_required_column() -> None:
    frame = ohlcv_frame().drop(columns=["volume"])

    with pytest.raises(OHLCVSchemaError, match="missing required columns"):
        validate_ohlcv_schema(frame)


def test_validate_ohlcv_schema_rejects_non_numeric_price() -> None:
    frame = ohlcv_frame()
    frame["close"] = frame["close"].astype(object)
    frame.loc[1, "close"] = "bad"

    with pytest.raises(OHLCVSchemaError, match="close"):
        validate_ohlcv_schema(frame)
