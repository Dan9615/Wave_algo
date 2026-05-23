import pandas as pd

from wave_algo.timeframes import completed_frame_asof, timeframe_duration


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=4, freq="15min"),
            "open": [100, 101, 102, 103],
            "high": [101, 102, 103, 104],
            "low": [99, 100, 101, 102],
            "close": [100, 101, 102, 103],
            "volume": [1000, 1000, 1000, 1000],
        }
    )


def test_timeframe_duration_parses_supported_compact_labels() -> None:
    assert timeframe_duration("15m") == pd.Timedelta(minutes=15)
    assert timeframe_duration("1h") == pd.Timedelta(hours=1)
    assert timeframe_duration("4h") == pd.Timedelta(hours=4)
    assert timeframe_duration("1d") == pd.Timedelta(days=1)
    assert timeframe_duration("daily") == pd.Timedelta(days=1)


def test_completed_frame_asof_uses_bar_completion_times() -> None:
    result = completed_frame_asof(
        frame(),
        timeframe="15m",
        signal_time=pd.Timestamp("2026-01-01 00:45"),
    )

    assert result["timestamp"].tolist() == [
        pd.Timestamp("2026-01-01 00:00"),
        pd.Timestamp("2026-01-01 00:15"),
        pd.Timestamp("2026-01-01 00:30"),
    ]
