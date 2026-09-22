from jev_chess.board_viz import (
    arrow_style,
    confidence_meter,
    confidence_text,
    format_json_lines,
    preview_usable,
    probs_to_arrows,
    should_auto_step,
)


def test_arrows_ranked_filtered():
    probs = {"e2e4": 0.61, "g1f3": 0.28, "d2d4": 0.08, "c2c4": 0.03}
    arrows = probs_to_arrows(probs, top_k=5, min_p=0.05)
    assert [a.uci for a in arrows] == ["e2e4", "g1f3", "d2d4"]
    assert [a.rank for a in arrows] == [0, 1, 2]
    assert arrows[0].from_square != arrows[0].to_square


def test_arrows_top_k_and_invalid():
    probs = {"e2e4": 0.5, "bogus": 0.4, "d2d4": 0.1}
    arrows = probs_to_arrows(probs, top_k=1, min_p=0.0)
    assert len(arrows) == 1 and arrows[0].uci == "e2e4"


def test_top_k_controls_count():
    probs = {m: p for m, p in [
        ("e2e4", 0.40), ("d2d4", 0.20), ("g1f3", 0.12), ("c2c4", 0.08),
        ("e2e3", 0.06), ("d2d3", 0.05), ("g2g3", 0.04), ("b2b3", 0.03),
        ("a2a3", 0.02),
    ]}
    assert len(probs_to_arrows(probs, top_k=3, min_p=0.01)) == 3
    assert len(probs_to_arrows(probs, top_k=5, min_p=0.01)) == 5
    assert len(probs_to_arrows(probs, top_k=8, min_p=0.01)) == 8
    assert len(probs_to_arrows(probs, top_k=None, min_p=0.0)) == 9
    assert len(probs_to_arrows(probs, top_k=None, min_p=0.05)) == 6


def test_arrow_style_monotonic():
    w1, a1 = arrow_style(0.6, 0.6)
    w2, a2 = arrow_style(0.2, 0.6)
    assert (w1, a1) > (w2, a2)


def test_autoplay_matrix():
    assert should_auto_step("off", "white", True, False) is False
    assert should_auto_step("on", "white", True, False) is True
    assert should_auto_step("on", "black", True, False) is True
    assert should_auto_step("opponent", "white", True, False) is False
    assert should_auto_step("opponent", "black", True, False) is True
    assert should_auto_step("on", "white", False, False) is False  # viewing history
    assert should_auto_step("on", "white", True, True) is False  # game over


def test_confidence_words():
    assert "very sure" in confidence_text(0.9)
    assert "guessing" in confidence_text(0.1)
    assert "not reported" in confidence_text(None)


def test_confidence_meter_thresholds_match_words():
    assert confidence_meter(None) == (0.0, (100, 100, 105))
    frac, color = confidence_meter(0.9)
    assert frac == 0.9 and color == (74, 160, 90)
    assert confidence_meter(0.6)[1] == (210, 170, 40)
    assert confidence_meter(0.4)[1] == (220, 130, 40)
    assert confidence_meter(0.1)[1] == (200, 70, 70)
    assert confidence_meter(1.5)[0] == 1.0
    assert confidence_meter(-0.2)[0] == 0.0


def test_preview_usable():
    assert preview_usable("fen1", "fen1", True, True, False) is True
    assert preview_usable("fen1", "fen2", True, True, False) is False  # stale position
    assert preview_usable(None, "fen1", True, True, False) is False  # nothing cached
    assert preview_usable("fen1", "fen1", False, True, False) is False  # engine turn
    assert preview_usable("fen1", "fen1", True, False, False) is False  # viewing history
    assert preview_usable("fen1", "fen1", True, True, True) is False  # game over


def test_format_json_lines():
    lines = format_json_lines({"a": 1, "b": [1, 2]})
    import json

    assert json.loads("\n".join(lines)) == {"a": 1, "b": [1, 2]}
