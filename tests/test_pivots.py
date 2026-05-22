import pandas as pd

from wave_algo.pivots import ZigZagParams, detect_pivots


def test_zigzag_pivots_use_percentage_atr_and_distance_filters() -> None:
    prices = [100, 101, 100.5, 111, 110, 108, 103, 104, 95, 96, 94]
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(prices), freq="h"),
            "open": prices,
            "high": [price + 0.5 for price in prices],
            "low": [price - 0.5 for price in prices],
            "close": prices,
            "volume": [100] * len(prices),
        }
    )

    pivots = detect_pivots(
        df,
        ZigZagParams(
            reversal_pct=0.05,
            atr_period=3,
            atr_multiplier=0.1,
            min_bars_between_pivots=2,
        ),
    )

    assert [pivot.kind.value for pivot in pivots] == ["low", "high", "low"]
    assert pivots[0].price == 99.5
    assert pivots[1].price == 111.5
    assert pivots[2].price == 93.5


def test_zigzag_accepts_custom_timestamp_column() -> None:
    prices = [100, 106, 99, 107, 98]
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=len(prices), freq="h"),
            "open": prices,
            "high": [price + 0.5 for price in prices],
            "low": [price - 0.5 for price in prices],
            "close": prices,
            "volume": [100] * len(prices),
        }
    )

    pivots = detect_pivots(
        df,
        ZigZagParams(
            reversal_pct=0.05,
            atr_period=2,
            atr_multiplier=0.0,
            min_bars_between_pivots=1,
            timestamp_column="time",
        ),
    )

    assert pivots
    assert all(pivot.time is not None for pivot in pivots)
