from wave_algo.models import HTFState
from wave_algo.scoring import SCORE_WEIGHTS, calculate_score, htf_alignment_score


def test_confidence_scoring_uses_fixed_mvp_weights() -> None:
    breakdown = calculate_score(
        fibonacci_fit=1.0,
        htf_alignment=1.0,
        channel_fit=1.0,
        volume_confirmation=1.0,
        momentum_confirmation=1.0,
        alternation_time=1.0,
    )

    assert breakdown.to_dict() == {
        "fibonacci_fit": SCORE_WEIGHTS["fibonacci_fit"],
        "htf_alignment": SCORE_WEIGHTS["htf_alignment"],
        "channel_fit": SCORE_WEIGHTS["channel_fit"],
        "volume_confirmation": SCORE_WEIGHTS["volume_confirmation"],
        "momentum_confirmation": SCORE_WEIGHTS["momentum_confirmation"],
        "alternation_time": SCORE_WEIGHTS["alternation_time"],
        "total": 100.0,
    }


def test_htf_alignment_scores_directionally() -> None:
    assert htf_alignment_score("long", HTFState(state="bullish")) == 1.0
    assert htf_alignment_score("short", HTFState(state="bearish")) == 1.0
    assert htf_alignment_score("long", HTFState(state="bearish")) == 0.0
    assert htf_alignment_score("short", HTFState(state="neutral")) == 0.5
