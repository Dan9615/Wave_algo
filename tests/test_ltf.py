from pathlib import Path

import pandas as pd

from wave_algo.ltf import (
    LTFContext,
    analyze_ltf_ohlcv,
    evaluate_signal_ltf_confirmation,
    filter_signals_by_ltf,
    load_ltf_context,
)
from wave_algo.models import ScoreBreakdown, SignalTarget, TradeSignal
from wave_algo.pivots import ZigZagParams


def ltf_frame(
    prices: list[float],
    *,
    start: str = "2026-01-01",
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=len(prices), freq="15min"),
            "open": prices,
            "high": [price + 0.5 for price in prices],
            "low": [price - 0.5 for price in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        }
    )


def ltf_params() -> ZigZagParams:
    return ZigZagParams(
        reversal_pct=0.03,
        atr_period=2,
        min_bars_between_pivots=1,
    )


def context(frame: pd.DataFrame) -> LTFContext:
    return LTFContext(
        symbol="BTCUSDT",
        confirmation=analyze_ltf_ohlcv(
            frame,
            timeframe="15m",
            pivot_params=ltf_params(),
        ),
    )


def signal(direction: str = "long") -> TradeSignal:
    return TradeSignal(
        symbol="BTCUSDT",
        timeframe="1h",
        setup_type="wave_3",
        direction=direction,
        signal_time=pd.Timestamp("2026-01-01 00:00"),
        entry=108 if direction == "long" else 100,
        stop=100 if direction == "long" else 108,
        targets=(SignalTarget("tp1", 120 if direction == "long" else 90, 1.0),),
        confidence=80,
        score_breakdown=ScoreBreakdown(),
    )


def test_ltf_filter_allows_aligned_bullish_and_bearish_confirmation() -> None:
    bullish = filter_signals_by_ltf(
        [signal("long")],
        {"BTCUSDT": context(ltf_frame([100, 106, 103, 108.7]))},
        lookback_bars=8,
    )
    bearish = filter_signals_by_ltf(
        [signal("short")],
        {"BTCUSDT": context(ltf_frame([108.7, 103, 106, 100]))},
        lookback_bars=8,
    )

    assert len(bullish.allowed_signals) == 1
    assert bullish.block_reasons == {}
    assert bullish.decisions[0].confirmation["completed_rows"] == 4
    assert bullish.decisions[0].confirmation["matched"]["direction"] == "long"
    assert len(bearish.allowed_signals) == 1
    assert bearish.block_reasons == {}
    assert bearish.decisions[0].confirmation["matched"]["direction"] == "short"


def test_ltf_filter_blocks_missing_and_opposite_confirmation(tmp_path: Path) -> None:
    missing = load_ltf_context("BTCUSDT", tmp_path, pivot_params=ltf_params())
    missing_result = filter_signals_by_ltf(
        [signal("long")],
        {"BTCUSDT": missing},
        lookback_bars=8,
    )
    opposite_result = filter_signals_by_ltf(
        [signal("long")],
        {"BTCUSDT": context(ltf_frame([108.7, 103, 106, 100]))},
        lookback_bars=8,
    )

    assert missing_result.allowed_signals == ()
    assert missing_result.block_reasons == {"15m_unavailable": 1}
    assert not missing.confirmation.available
    assert opposite_result.allowed_signals == ()
    assert opposite_result.block_reasons == {"15m_no_bullish_confirmation": 1}


def test_ltf_confirmation_is_stable_when_future_bars_are_added() -> None:
    prefix = ltf_frame([100, 106, 103, 108.7])
    future = ltf_frame([90, 94, 91, 88], start="2026-01-01 01:00")
    full = pd.concat([prefix, future], ignore_index=True)

    prefix_result = filter_signals_by_ltf(
        [signal("long")],
        {"BTCUSDT": context(prefix)},
        lookback_bars=8,
    )
    full_result = filter_signals_by_ltf(
        [signal("long")],
        {"BTCUSDT": context(full)},
        lookback_bars=8,
    )

    assert len(prefix_result.allowed_signals) == 1
    assert len(full_result.allowed_signals) == 1
    assert prefix_result.decisions[0].confirmation["completed_rows"] == 4
    assert full_result.decisions[0].confirmation["completed_rows"] == 4
    assert prefix_result.decisions[0].confirmation["matched"] == (
        full_result.decisions[0].confirmation["matched"]
    )


def test_ltf_filter_rejects_non_positive_lookback() -> None:
    loaded_context = context(ltf_frame([100, 106, 103, 108.7]))

    try:
        filter_signals_by_ltf(
            [signal("long")],
            {"BTCUSDT": loaded_context},
            lookback_bars=0,
        )
    except ValueError as exc:
        assert str(exc) == "lookback_bars must be positive"
    else:
        raise AssertionError("expected non-positive filter lookback to fail")

    try:
        evaluate_signal_ltf_confirmation(
            signal("long"),
            loaded_context,
            lookback_bars=0,
        )
    except ValueError as exc:
        assert str(exc) == "lookback_bars must be positive"
    else:
        raise AssertionError("expected non-positive signal lookback to fail")
