import json
from pathlib import Path

import pandas as pd

from wave_algo.cli import main
from wave_algo.pivots import ZigZagParams, detect_pivot_confirmations
from wave_algo.signals import generate_signals_from_ohlcv


def candidate_frame() -> pd.DataFrame:
    prices = [100, 110, 104, 121, 116, 132, 118, 130, 122, 128, 124, 131]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(prices), freq="h"),
            "open": prices,
            "high": [price + 0.5 for price in prices],
            "low": [price - 0.5 for price in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        }
    )


def bullish_htf_frame() -> pd.DataFrame:
    prices = [100, 110, 104, 125, 117, 132]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-12-31", periods=len(prices), freq="4h"),
            "open": prices,
            "high": [price + 0.5 for price in prices],
            "low": [price - 0.5 for price in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        }
    )


def neutral_daily_frame() -> pd.DataFrame:
    prices = [100, 101]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-12-30", periods=len(prices), freq="1D"),
            "open": prices,
            "high": [price + 0.5 for price in prices],
            "low": [price - 0.5 for price in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        }
    )


def test_generate_signals_from_ohlcv_scans_wave_and_triangle_candidates() -> None:
    signals = generate_signals_from_ohlcv(
        candidate_frame(),
        symbol="BTCUSDT",
        timeframe="1h",
        htf_state="bullish",
        pivot_params=ZigZagParams(
            reversal_pct=0.03,
            atr_period=2,
            min_bars_between_pivots=1,
        ),
    )

    setup_types = {signal.setup_type for signal in signals}
    assert {"wave_3", "wave_5", "triangle_breakout"}.issubset(setup_types)
    assert all(signal.params["generated_from_ohlcv"] for signal in signals)
    assert all(signal.params["generation_mode"] == "point_in_time" for signal in signals)


def test_full_frame_signal_generation_is_diagnostic_opt_in() -> None:
    pivot_params = ZigZagParams(
        reversal_pct=0.03,
        atr_period=2,
        min_bars_between_pivots=1,
    )
    point_in_time_signals = generate_signals_from_ohlcv(
        candidate_frame(),
        symbol="BTCUSDT",
        timeframe="1h",
        htf_state="bullish",
        pivot_params=pivot_params,
    )
    full_frame_signals = generate_signals_from_ohlcv(
        candidate_frame(),
        symbol="BTCUSDT",
        timeframe="1h",
        htf_state="bullish",
        pivot_params=pivot_params,
        point_in_time=False,
    )

    assert point_in_time_signals
    assert full_frame_signals
    assert {signal.params["generation_mode"] for signal in point_in_time_signals} == {
        "point_in_time"
    }
    assert {signal.params["generation_mode"] for signal in full_frame_signals} == {
        "full_frame"
    }
    assert min(signal.params["signal_index"] for signal in full_frame_signals) < min(
        signal.params["signal_index"] for signal in point_in_time_signals
    )


def test_point_in_time_generation_is_stable_when_future_bars_are_added() -> None:
    df = candidate_frame()
    pivot_params = ZigZagParams(
        reversal_pct=0.03,
        atr_period=2,
        min_bars_between_pivots=1,
    )
    full_signals = generate_signals_from_ohlcv(
        df,
        symbol="BTCUSDT",
        timeframe="1h",
        htf_state="bullish",
        pivot_params=pivot_params,
    )

    for end in range(2, len(df) + 1):
        prefix = df.iloc[:end]
        prefix_end_time = prefix.iloc[-1]["timestamp"]
        prefix_signals = generate_signals_from_ohlcv(
            prefix,
            symbol="BTCUSDT",
            timeframe="1h",
            htf_state="bullish",
            pivot_params=pivot_params,
        )
        full_asof_prefix = [
            signal
            for signal in full_signals
            if signal.signal_time <= prefix_end_time
        ]

        assert _signal_identity(prefix_signals) == _signal_identity(full_asof_prefix)


def test_generated_signal_time_and_index_use_confirmation_or_breakout_bar() -> None:
    df = candidate_frame()
    pivot_params = ZigZagParams(
        reversal_pct=0.03,
        atr_period=2,
        min_bars_between_pivots=1,
    )
    confirmations = detect_pivot_confirmations(
        df,
        pivot_params,
        include_unconfirmed_terminal=False,
    )
    confirmation_by_pivot_index = {
        confirmation.pivot.index: confirmation.confirmation_index
        for confirmation in confirmations
    }

    signals = generate_signals_from_ohlcv(
        df,
        symbol="BTCUSDT",
        timeframe="1h",
        htf_state="bullish",
        pivot_params=pivot_params,
    )

    assert signals
    for signal in signals:
        signal_index = signal.params["signal_index"]
        source_confirmation_index = max(
            confirmation_by_pivot_index[pivot.index]
            for pivot in signal.source_pivots
        )
        assert signal.signal_time == df.iloc[signal_index]["timestamp"]
        assert signal_index >= source_confirmation_index
        assert signal_index >= signal.source_pivots[-1].index

    wave_signals = [
        signal
        for signal in signals
        if signal.setup_type in {"wave_3", "wave_5"}
    ]
    assert wave_signals
    assert all(
        signal.params["signal_index"] == signal.params["confirmation_index"]
        for signal in wave_signals
    )
    assert all(
        signal.params["signal_index"] > signal.source_pivots[-1].index
        for signal in wave_signals
    )


def _signal_identity(signals: list) -> list[tuple]:
    return [
        (
            signal.setup_type,
            signal.direction.value,
            signal.signal_time,
            signal.params["signal_index"],
            tuple(pivot.index for pivot in signal.source_pivots),
        )
        for signal in signals
    ]


def test_cli_backtest_smoke_uses_temp_parquet_fixture(
    tmp_path: Path,
    capsys,
) -> None:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    candidate_frame().to_parquet(data_dir / "BTCUSDT_1h.parquet", engine="pyarrow")
    bullish_htf_frame().to_parquet(data_dir / "BTCUSDT_4h.parquet", engine="pyarrow")
    neutral_daily_frame().to_parquet(data_dir / "BTCUSDT_1d.parquet", engine="pyarrow")

    exit_code = main(
        [
            "backtest",
            "--data-dir",
            str(data_dir),
            "--symbols",
            "BTCUSDT",
            "--timeframes",
            "1h",
            "--reversal-pct",
            "0.03",
            "--atr-period",
            "2",
            "--min-bars-between-pivots",
            "1",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["signal_count"] > 0
    assert set(payload["thresholds"]) == {"60", "70", "80"}
    assert payload["pivot_params"]["min_bars_between_pivots"] == 1
    assert payload["htf_filter"]["enabled"]
    assert payload["htf_filter"]["mode"] == "point_in_time_completed_bars"
    assert payload["htf_filter"]["availability"]["BTCUSDT"]["alignment"]["available"]
    assert payload["htf_filter"]["availability"]["BTCUSDT"]["alignment"]["state"]["state"] == (
        "bullish"
    )
    assert payload["htf_filter"]["allowed_signal_count"] > 0
    assert payload["htf_filter"]["blocked_signal_count"] > 0
    assert payload["backtested_signal_count"] == payload["htf_filter"]["allowed_signal_count"]
    threshold_70 = payload["thresholds"]["70"]
    assert threshold_70["trade_count"] + threshold_70["skipped_signals"] == (
        payload["backtested_signal_count"]
    )


def test_cli_backtest_can_run_unfiltered_diagnostics(
    tmp_path: Path,
    capsys,
) -> None:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    candidate_frame().to_parquet(data_dir / "BTCUSDT_1h.parquet", engine="pyarrow")

    exit_code = main(
        [
            "backtest",
            "--data-dir",
            str(data_dir),
            "--symbols",
            "BTCUSDT",
            "--timeframes",
            "1h",
            "--no-htf-filter",
            "--reversal-pct",
            "0.03",
            "--atr-period",
            "2",
            "--min-bars-between-pivots",
            "1",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["signal_count"] > 0
    assert payload["backtested_signal_count"] == payload["signal_count"]
    assert payload["htf_filter"] == {
        "enabled": False,
        "mode": "unfiltered",
        "alignment_timeframe": "4h",
        "veto_timeframes": ["1d", "daily"],
        "availability": {},
        "generated_signal_count": payload["signal_count"],
        "allowed_signal_count": payload["signal_count"],
        "blocked_signal_count": 0,
        "block_reasons": {},
    }
