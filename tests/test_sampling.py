from jev_chess.sampling import sample_move, tempered_distribution


def test_greedy_is_argmax():
    probs = {"e2e4": 0.6, "d2d4": 0.3, "g1f3": 0.1}
    assert tempered_distribution(probs, 0.0) == {"e2e4": 1.0, "d2d4": 0.0, "g1f3": 0.0}
    assert sample_move(probs, temperature=0.0) == "e2e4"


def test_temperature_one_preserves():
    probs = {"a": 0.5, "b": 0.3, "c": 0.2}
    out = tempered_distribution(probs, 1.0)
    assert out == probs


def test_high_temperature_flattens():
    probs = {"a": 0.9, "b": 0.1}
    out = tempered_distribution(probs, 10.0)
    assert abs(out["a"] - out["b"]) < abs(0.9 - 0.1)
    assert abs(sum(out.values()) - 1.0) < 1e-9


def test_low_temperature_sharpens():
    probs = {"a": 0.6, "b": 0.4}
    out = tempered_distribution(probs, 0.1)
    assert out["a"] > 0.6
    assert abs(sum(out.values()) - 1.0) < 1e-9


def test_zero_stays_zero():
    probs = {"a": 1.0, "b": 0.0}
    out = tempered_distribution(probs, 2.0)
    assert out["b"] == 0.0
    assert out["a"] == 1.0


def test_seeded_sampling_deterministic():
    probs = {"e2e4": 0.5, "d2d4": 0.5}
    assert sample_move(probs, 1.0, seed=42) == sample_move(probs, 1.0, seed=42)
