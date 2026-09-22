"""Temperature sampling over a Jev Choice distribution.

Single function covers greedy / sample / sharpen / flatten:
  T=0   -> argmax (greedy)
  T=1   -> sample raw distribution
  T<1   -> sharper, T>1 -> flatter: p_T(i) propto p_i ** (1/T)
"""

from __future__ import annotations

import math
import random


def tempered_distribution(probs: dict[str, float], temperature: float) -> dict[str, float]:
    if temperature < 0:
        raise ValueError("temperature must be >= 0")
    if not probs:
        raise ValueError("probs must not be empty")
    if any(p < 0 for p in probs.values()):
        raise ValueError("probabilities must be >= 0")
    total = sum(probs.values())
    if total <= 0:
        raise ValueError("probabilities must sum to > 0")

    if temperature == 0:
        best = max(probs.values())
        winners = [k for k, p in probs.items() if p == best]
        # Deterministic tiebreak: sorted order, first wins. Sampling fn handles seed if needed.
        chosen = sorted(winners)[0]
        return {k: (1.0 if k == chosen else 0.0) for k in probs}

    inv_t = 1.0 / temperature
    powered = {k: (p**inv_t if p > 0 else 0.0) for k, p in probs.items()}
    norm = sum(powered.values())
    if norm <= 0 or not math.isfinite(norm):
        raise ValueError("tempered distribution is degenerate")
    return {k: v / norm for k, v in powered.items()}


def sample_move(
    probs: dict[str, float],
    temperature: float = 0.0,
    seed: int | None = None,
) -> str:
    """Return a UCI string sampled from (possibly tempered) distribution."""
    dist = tempered_distribution(probs, temperature)
    if temperature == 0:
        # tempered_distribution already collapsed to one-hot with sorted tiebreak
        return max(dist, key=lambda k: dist[k])
    rng = random.Random(seed)
    keys = sorted(dist)  # sorted for determinism given seed
    weights = [dist[k] for k in keys]
    return rng.choices(keys, weights=weights, k=1)[0]
