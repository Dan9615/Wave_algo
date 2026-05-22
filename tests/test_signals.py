from wave_algo.models import HTFState, Pivot
from wave_algo.signals import (
    calculate_triangle_signal,
    calculate_wave3_signal,
    calculate_wave5_signal,
)


def p(index: int, price: float, kind: str) -> Pivot:
    return Pivot(index=index, time=f"t{index}", price=price, kind=kind)


def test_wave3_signal_contains_full_diagnostics() -> None:
    pivots = [p(0, 100, "low"), p(1, 110, "high"), p(2, 104, "low")]

    signal = calculate_wave3_signal(
        pivots,
        symbol="BTCUSDT",
        timeframe="1h",
        direction="long",
        htf_state=HTFState(state="bullish", timeframe="4h", reason="synthetic"),
    )

    assert signal is not None
    payload = signal.to_dict()
    assert {
        "symbol",
        "timeframe",
        "setup_type",
        "direction",
        "signal_time",
        "entry",
        "stop",
        "targets",
        "confidence",
        "score_breakdown",
        "htf_state",
        "invalidation",
        "source_pivots",
        "params",
    }.issubset(payload)
    assert payload["setup_type"] == "wave_3"
    assert payload["direction"] == "long"
    assert payload["entry"] == 104
    assert payload["stop"] == 100
    assert len(payload["targets"]) == 2
    assert payload["confidence"] == payload["score_breakdown"]["total"]


def test_wave3_short_signal_inverts_entry_stop_and_targets() -> None:
    pivots = [p(0, 100, "high"), p(1, 90, "low"), p(2, 96, "high")]

    signal = calculate_wave3_signal(
        pivots,
        symbol="ETHUSDT",
        timeframe="1h",
        direction="short",
        htf_state="bearish",
    )

    assert signal is not None
    assert signal.entry == 96
    assert signal.stop == 100
    assert signal.targets[0].price < signal.entry
    assert signal.targets[1].price < signal.targets[0].price


def test_wave3_false_positive_rejected_when_retracement_misses_fib_zone() -> None:
    pivots = [p(0, 100, "low"), p(1, 110, "high"), p(2, 109, "low")]

    signal = calculate_wave3_signal(
        pivots,
        symbol="BTCUSDT",
        timeframe="1h",
        direction="long",
        htf_state="bullish",
    )

    assert signal is None


def test_wave5_signal_uses_wave4_invalidation_and_targets() -> None:
    pivots = [
        p(0, 100, "low"),
        p(1, 110, "high"),
        p(2, 104, "low"),
        p(3, 125, "high"),
        p(4, 116.978, "low"),
    ]

    signal = calculate_wave5_signal(
        pivots,
        symbol="BTCUSDT",
        timeframe="1h",
        direction="long",
        htf_state="bullish",
    )

    assert signal is not None
    assert signal.setup_type == "wave_5"
    assert signal.entry == 116.978
    assert signal.stop == 110
    assert signal.targets[0].price > signal.entry
    assert signal.targets[1].price > signal.targets[0].price
    assert "overlaps Wave 1" in signal.invalidation


def test_wave5_short_signal_inverts_direction() -> None:
    pivots = [
        p(0, 100, "high"),
        p(1, 90, "low"),
        p(2, 96, "high"),
        p(3, 75, "low"),
        p(4, 83.022, "high"),
    ]

    signal = calculate_wave5_signal(
        pivots,
        symbol="BTCUSDT",
        timeframe="1h",
        direction="short",
        htf_state="bearish",
    )

    assert signal is not None
    assert signal.entry == 83.022
    assert signal.stop == 90
    assert signal.targets[0].price < signal.entry
    assert signal.targets[1].price < signal.targets[0].price


def test_triangle_breakout_signal_measured_move() -> None:
    pivots = [
        p(0, 100, "low"),
        p(1, 110, "high"),
        p(2, 103, "low"),
        p(3, 108, "high"),
        p(4, 105, "low"),
    ]

    signal = calculate_triangle_signal(
        pivots,
        symbol="SOLUSDT",
        timeframe="1h",
        direction="long",
        breakout_price=109,
        htf_state="bullish",
    )

    assert signal is not None
    assert signal.setup_type == "triangle_breakout"
    assert signal.entry == 109
    assert signal.stop == 105
    assert signal.targets[0].price == 119
    assert signal.params["measured_width"] == 10
    assert signal.params["breakout_level"] == 106


def test_triangle_long_breakout_must_clear_upper_trendline() -> None:
    pivots = [
        p(0, 100, "low"),
        p(1, 110, "high"),
        p(2, 103, "low"),
        p(3, 108, "high"),
        p(4, 105, "low"),
    ]

    signal = calculate_triangle_signal(
        pivots,
        symbol="SOLUSDT",
        timeframe="1h",
        direction="long",
        breakout_price=105.5,
        htf_state="bullish",
    )

    assert signal is None


def test_triangle_short_breakout_signal_measured_move() -> None:
    pivots = [
        p(0, 110, "high"),
        p(1, 100, "low"),
        p(2, 107, "high"),
        p(3, 102, "low"),
        p(4, 105, "high"),
    ]

    signal = calculate_triangle_signal(
        pivots,
        symbol="SOLUSDT",
        timeframe="1h",
        direction="short",
        breakout_price=101,
        htf_state="bearish",
    )

    assert signal is not None
    assert signal.entry == 101
    assert signal.stop == 105
    assert signal.targets[0].price == 91
    assert signal.params["breakout_level"] == 104


def test_triangle_short_breakout_must_clear_lower_trendline() -> None:
    pivots = [
        p(0, 110, "high"),
        p(1, 100, "low"),
        p(2, 107, "high"),
        p(3, 102, "low"),
        p(4, 105, "high"),
    ]

    signal = calculate_triangle_signal(
        pivots,
        symbol="SOLUSDT",
        timeframe="1h",
        direction="short",
        breakout_price=104.5,
        htf_state="bearish",
    )

    assert signal is None
