from pathlib import Path

import pandas as pd

from wave_algo.htf import (
    HTFContext,
    HTFTimeframeResult,
    filter_signals_by_htf,
    infer_htf_state_from_ohlcv,
    infer_htf_state_from_pivots,
    load_htf_context,
)
from wave_algo.models import HTFState, Pivot, ScoreBreakdown, SignalTarget, TradeSignal
from wave_algo.pivots import ZigZagParams


def p(index: int, price: float, kind: str) -> Pivot:
    return Pivot(index=index, time=index, price=price, kind=kind)


def frame(prices: list[float], freq: str = "4h") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(prices), freq=freq),
            "open": prices,
            "high": [price + 0.5 for price in prices],
            "low": [price - 0.5 for price in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        }
    )


def htf_params() -> ZigZagParams:
    return ZigZagParams(
        reversal_pct=0.03,
        atr_period=2,
        min_bars_between_pivots=1,
    )


def signal(
    direction: str = "long",
    symbol: str = "BTCUSDT",
    signal_time: str | pd.Timestamp = "2026-01-01",
) -> TradeSignal:
    return TradeSignal(
        symbol=symbol,
        timeframe="1h",
        setup_type="wave_3",
        direction=direction,
        signal_time=pd.Timestamp(signal_time),
        entry=100,
        stop=90 if direction == "long" else 110,
        targets=(SignalTarget("tp1", 120 if direction == "long" else 80, 1.0),),
        confidence=80,
        score_breakdown=ScoreBreakdown(),
    )


def timeframe_result(
    timeframe: str,
    state: str,
    *,
    available: bool = True,
) -> HTFTimeframeResult:
    return HTFTimeframeResult(
        timeframe=timeframe,
        state=HTFState(state=state, timeframe=timeframe, reason="synthetic"),
        available=available,
    )


def context(
    *,
    alignment_state: str,
    veto_state: str = "neutral",
    alignment_available: bool = True,
) -> HTFContext:
    alignment = timeframe_result(
        "4h",
        alignment_state,
        available=alignment_available,
    )
    veto = timeframe_result("1d", veto_state)
    return HTFContext(
        symbol="BTCUSDT",
        alignment=alignment,
        veto=veto,
        timeframes={"4h": alignment, "1d": veto},
    )


def test_infer_htf_state_from_ohlcv_validates_bullish_and_bearish_impulses() -> None:
    bullish = infer_htf_state_from_ohlcv(
        frame([100, 110, 104, 125, 117, 132]),
        timeframe="4h",
        pivot_params=htf_params(),
    )
    bearish = infer_htf_state_from_ohlcv(
        frame([132, 120, 126, 105, 113, 100]),
        timeframe="4h",
        pivot_params=htf_params(),
    )

    assert bullish.state == "bullish"
    assert "complete_impulse" in bullish.reason
    assert bearish.state == "bearish"
    assert "complete_impulse" in bearish.reason


def test_infer_htf_state_falls_back_to_neutral_for_invalid_or_insufficient_pivots() -> None:
    invalid = infer_htf_state_from_pivots(
        [p(0, 100, "low"), p(1, 110, "high"), p(2, 99, "low")],
        timeframe="4h",
    )
    insufficient = infer_htf_state_from_pivots(
        [p(0, 100, "low"), p(1, 110, "high")],
        timeframe="4h",
    )

    assert invalid.state == "neutral"
    assert "wave2_breach" in invalid.reason
    assert insufficient.state == "neutral"
    assert "fewer than three pivots" in insufficient.reason


def test_load_htf_context_uses_optional_parquet_contract_and_daily_alias(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    frame([100, 110, 104, 125, 117, 132]).to_parquet(
        data_dir / "BTCUSDT_4h.parquet",
        engine="pyarrow",
    )
    frame([100, 101], freq="1D").to_parquet(
        data_dir / "BTCUSDT_daily.parquet",
        engine="pyarrow",
    )

    loaded = load_htf_context(
        "BTCUSDT",
        data_dir,
        veto_timeframes=("1d", "daily"),
        pivot_params=htf_params(),
    )

    assert loaded.alignment.available
    assert loaded.alignment.state.state == "bullish"
    assert not loaded.timeframes["1d"].available
    assert loaded.veto.timeframe == "daily"
    assert loaded.veto.state.state == "neutral"


def test_htf_filter_requires_4h_alignment_and_applies_daily_veto() -> None:
    long_signal = signal("long")
    short_signal = signal("short")

    aligned = filter_signals_by_htf(
        [long_signal, short_signal],
        {"BTCUSDT": context(alignment_state="bullish")},
    )
    vetoed = filter_signals_by_htf(
        [long_signal],
        {"BTCUSDT": context(alignment_state="bullish", veto_state="bearish")},
    )

    assert len(aligned.allowed_signals) == 1
    assert aligned.allowed_signals[0].direction.value == "long"
    assert aligned.allowed_signals[0].htf_state.state == "bullish"
    assert aligned.block_reasons == {"4h_bullish_not_bearish": 1}
    assert vetoed.allowed_signals == ()
    assert vetoed.block_reasons == {"daily_bearish_veto": 1}


def test_missing_4h_data_blocks_filtered_signals(tmp_path: Path) -> None:
    loaded = load_htf_context("BTCUSDT", tmp_path, pivot_params=htf_params())
    result = filter_signals_by_htf([signal("long")], {"BTCUSDT": loaded})

    assert not loaded.alignment.available
    assert result.allowed_signals == ()
    assert result.block_reasons == {"4h_unavailable": 1}


def test_htf_filter_uses_only_completed_bars_as_of_signal_time(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    frame([100, 110, 104, 125, 117, 132]).to_parquet(
        data_dir / "BTCUSDT_4h.parquet",
        engine="pyarrow",
    )
    loaded = load_htf_context("BTCUSDT", data_dir, pivot_params=htf_params())

    filtered = filter_signals_by_htf(
        [
            signal("long", signal_time="2026-01-01 04:00"),
            signal("long", signal_time="2026-01-02 00:00"),
        ],
        {"BTCUSDT": loaded},
    )

    assert loaded.alignment.state.state == "bullish"
    assert len(filtered.allowed_signals) == 1
    assert filtered.allowed_signals[0].signal_time == pd.Timestamp("2026-01-02")
    assert filtered.allowed_signals[0].score_breakdown.htf_alignment == 20.0
    assert filtered.block_reasons == {"4h_neutral_not_bullish": 1}


def test_daily_veto_uses_only_completed_bars_as_of_signal_time(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    frame([100, 110, 104, 125, 117, 132]).to_parquet(
        data_dir / "BTCUSDT_4h.parquet",
        engine="pyarrow",
    )
    frame([132, 120, 126, 105, 113, 100], freq="1D").to_parquet(
        data_dir / "BTCUSDT_1d.parquet",
        engine="pyarrow",
    )
    loaded = load_htf_context("BTCUSDT", data_dir, pivot_params=htf_params())

    filtered = filter_signals_by_htf(
        [
            signal("long", signal_time="2026-01-02 00:00"),
            signal("long", signal_time="2026-01-07 00:00"),
        ],
        {"BTCUSDT": loaded},
    )

    assert loaded.veto.state.state == "bearish"
    assert len(filtered.allowed_signals) == 1
    assert filtered.allowed_signals[0].signal_time == pd.Timestamp("2026-01-02")
    assert filtered.block_reasons == {"daily_bearish_veto": 1}
