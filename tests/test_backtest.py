import pandas as pd
from pytest import approx

from wave_algo.backtest import BacktestConfig, run_backtest
from wave_algo.models import ScoreBreakdown, SignalTarget, TradeSignal


def market_frame(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(opens), freq="h"),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000] * len(opens),
        }
    )


def signal(
    df: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    setup_type: str = "wave_3",
    direction: str = "long",
    signal_index: int = 0,
    stop: float = 90,
    targets: tuple[SignalTarget, ...] = (SignalTarget("tp1", 120, 1.0),),
    confidence: float = 80,
) -> TradeSignal:
    return TradeSignal(
        symbol=symbol,
        timeframe="1h",
        setup_type=setup_type,
        direction=direction,
        signal_time=df.iloc[signal_index]["timestamp"],
        entry=float(df.iloc[signal_index]["close"]),
        stop=stop,
        targets=targets,
        confidence=confidence,
        score_breakdown=ScoreBreakdown(),
    )


def test_backtest_uses_next_open_and_stop_first_same_bar_collision() -> None:
    df = market_frame(
        opens=[100, 100, 100],
        highs=[101, 111, 101],
        lows=[99, 94, 99],
        closes=[100, 100, 100],
    )

    result = run_backtest(
        {("BTCUSDT", "1h"): df},
        [signal(df, stop=95, targets=(SignalTarget("tp1", 110, 1.0),))],
        threshold=70,
        config=BacktestConfig(initial_equity=10_000, fee_rate=0, slippage_rate=0),
    )

    trade = result.trades[0]
    assert trade.entry_index == 1
    assert trade.entry_price == 100
    assert trade.exit_reason == "stop_loss"
    assert trade.net_pnl == approx(-100)
    assert result.final_equity == approx(9_900)


def test_backtest_applies_fees_slippage_and_risk_sizing() -> None:
    df = market_frame(
        opens=[100, 100, 100],
        highs=[101, 120, 101],
        lows=[99, 100, 99],
        closes=[100, 110, 100],
    )

    result = run_backtest(
        {("BTCUSDT", "1h"): df},
        [signal(df, stop=99.9, targets=(SignalTarget("tp1", 110, 1.0),))],
        threshold=70,
        config=BacktestConfig(
            initial_equity=10_000,
            fee_rate=0.001,
            slippage_rate=0.01,
        ),
    )

    trade = result.trades[0]
    assert trade.entry_price == approx(101)
    assert trade.quantity == approx(10_000 * 0.01 / (101 - 99.9))
    assert trade.fills[-1].price == approx(108.9)
    assert trade.fees > 0
    assert trade.net_pnl < trade.gross_pnl


def test_position_size_is_capped_by_available_cash() -> None:
    df = market_frame(
        opens=[100, 100, 100],
        highs=[101, 120, 101],
        lows=[99, 99.95, 99],
        closes=[100, 110, 100],
    )

    result = run_backtest(
        {("BTCUSDT", "1h"): df},
        [signal(df, stop=99.9, targets=(SignalTarget("tp1", 110, 1.0),))],
        threshold=70,
        config=BacktestConfig(
            initial_equity=10_000,
            fee_rate=0,
            slippage_rate=0,
        ),
    )

    assert result.trades[0].quantity == approx(100)


def test_wave3_partial_exits_move_remaining_stop_to_breakeven() -> None:
    df = market_frame(
        opens=[100, 100, 106, 116],
        highs=[101, 105, 111, 121],
        lows=[99, 96, 101, 101],
        closes=[100, 104, 110, 120],
    )
    wave3 = signal(
        df,
        stop=90,
        targets=(
            SignalTarget("tp1", 110, 0.5),
            SignalTarget("tp2", 120, 0.5),
        ),
    )

    result = run_backtest(
        {("BTCUSDT", "1h"): df},
        [wave3],
        threshold=70,
        config=BacktestConfig(initial_equity=10_000, fee_rate=0, slippage_rate=0),
    )

    trade = result.trades[0]
    assert [fill.reason for fill in trade.fills] == ["entry_next_open", "tp1", "tp2"]
    assert [fill.quantity for fill in trade.fills[1:]] == [approx(5), approx(5)]
    assert trade.net_pnl == approx(150)


def test_partial_exit_remaining_size_can_stop_at_breakeven() -> None:
    df = market_frame(
        opens=[100, 100, 106],
        highs=[101, 111, 108],
        lows=[99, 96, 99],
        closes=[100, 110, 100],
    )
    wave3 = signal(
        df,
        stop=90,
        targets=(
            SignalTarget("tp1", 110, 0.5),
            SignalTarget("tp2", 120, 0.5),
        ),
    )

    result = run_backtest(
        {("BTCUSDT", "1h"): df},
        [wave3],
        threshold=70,
        config=BacktestConfig(initial_equity=10_000, fee_rate=0, slippage_rate=0),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "breakeven_stop"
    assert [fill.reason for fill in trade.fills] == [
        "entry_next_open",
        "tp1",
        "breakeven_stop",
    ]
    assert trade.net_pnl == approx(50)


def test_time_stop_exits_next_bar_open() -> None:
    df = market_frame(
        opens=[100, 100, 102],
        highs=[101, 105, 103],
        lows=[99, 96, 101],
        closes=[100, 101, 102],
    )

    result = run_backtest(
        {("BTCUSDT", "1h"): df},
        [signal(df, stop=90, targets=(SignalTarget("tp1", 120, 1.0),))],
        threshold=70,
        config=BacktestConfig(
            initial_equity=10_000,
            fee_rate=0,
            slippage_rate=0,
            time_stops={"wave_3": 1},
        ),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "time_stop"
    assert trade.exit_index == 2
    assert trade.fills[-1].price == 102


def test_portfolio_constraints_limit_symbols_and_total_positions() -> None:
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    data = {
        (symbol_name, "1h"): market_frame(
            opens=[100, 100, 101],
            highs=[101, 105, 106],
            lows=[99, 96, 97],
            closes=[100, 101, 102],
        )
        for symbol_name in symbols
    }
    signals = [
        signal(data[(symbol_name, "1h")], symbol=symbol_name, stop=90)
        for symbol_name in symbols
    ]
    duplicate_symbol = signal(data[("BTCUSDT", "1h")], symbol="BTCUSDT", stop=90)

    result = run_backtest(
        data,
        [*signals, duplicate_symbol],
        threshold=70,
        config=BacktestConfig(
            initial_equity=10_000,
            fee_rate=0,
            slippage_rate=0,
            max_positions=3,
            time_stops={"wave_3": 2},
        ),
    )

    assert len(result.trades) == 3
    reasons = [skipped["reason"] for skipped in result.skipped_signals]
    assert "max_portfolio_positions" in reasons


def test_same_bar_exit_does_not_free_symbol_for_same_open_signal() -> None:
    df = market_frame(
        opens=[100, 100, 100],
        highs=[101, 101, 101],
        lows=[99, 94, 94],
        closes=[100, 100, 100],
    )
    first = signal(df, setup_type="wave_3", stop=95)
    second = signal(df, setup_type="wave_5", stop=95)

    result = run_backtest(
        {("BTCUSDT", "1h"): df},
        [first, second],
        threshold=70,
        config=BacktestConfig(initial_equity=10_000, fee_rate=0, slippage_rate=0),
    )

    assert len(result.trades) == 1
    assert result.trades[0].setup_type == "wave_3"
    assert result.skipped_signals[0]["reason"] == "symbol_position_open"


def test_below_threshold_signals_are_excluded_from_backtest() -> None:
    df = market_frame(
        opens=[100, 100, 100],
        highs=[101, 111, 101],
        lows=[99, 96, 99],
        closes=[100, 110, 100],
    )

    result = run_backtest(
        {("BTCUSDT", "1h"): df},
        [signal(df, confidence=65)],
        threshold=70,
        config=BacktestConfig(initial_equity=10_000),
    )

    assert result.trades == ()
    assert result.skipped_signals[0]["reason"] == "below_confidence_threshold"
