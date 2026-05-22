import json
from pathlib import Path

import pandas as pd

from wave_algo.cli import main
from wave_algo.pivots import ZigZagParams
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


def test_cli_backtest_smoke_uses_temp_parquet_fixture(
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
