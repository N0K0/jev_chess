"""Pure (display-free) helpers for the board UI: arrows, autoplay, plain-language text.

Kept free of pygame so unit tests run headless.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

AUTOPLAY_MODES = ("off", "on", "opponent")


@dataclass
class ArrowViz:
    uci: str
    from_square: int
    to_square: int
    prob: float
    rank: int  # 0 = favourite


def probs_to_arrows(
    probs: dict[str, float], top_k: int | None = 5, min_p: float = 0.05
) -> list[ArrowViz]:
    """Top-K moves with prob >= min_p, ranked. top_k=None means no limit. Invalid UCIs are skipped."""
    ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    out: list[ArrowViz] = []
    for uci, p in ranked:
        if (top_k is not None and len(out) >= top_k) or p < min_p:
            break
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            continue
        out.append(
            ArrowViz(
                uci=uci,
                from_square=move.from_square,
                to_square=move.to_square,
                prob=float(p),
                rank=len(out),
            )
        )
    return out


def arrow_style(prob: float, max_prob: float) -> tuple[int, int]:
    """(width_px, alpha) scaled by probability. Monotonic in prob."""
    ratio = (prob / max_prob) if max_prob > 0 else 0.0
    width = 3 + round(7 * ratio)  # 3..10 px on a 720px board scale
    alpha = 70 + round(150 * ratio)  # 70..220
    return width, alpha


def should_auto_step(mode: str, side_to_move: str, at_tip: bool, game_over: bool) -> bool:
    """Autoplay decision. 'opponent' auto-plays Black (engine) only."""
    if mode not in AUTOPLAY_MODES:
        raise ValueError(f"unknown autoplay mode: {mode}")
    if mode == "off" or game_over or not at_tip:
        return False
    if mode == "on":
        return True
    return side_to_move == "black"  # opponent-only


def preview_usable(
    cached_fen: str | None,
    board_fen: str,
    white_to_move: bool,
    at_tip: bool,
    game_over: bool,
) -> bool:
    """A cached Jev distribution can be locked in only for the exact position it was fetched for."""
    return (
        cached_fen is not None
        and cached_fen == board_fen
        and white_to_move
        and at_tip
        and not game_over
    )


def side_to_move_text(board: chess.Board, game_over: bool) -> str:
    if game_over:
        return f"Game over — result {board.result()}"
    who = "Jev (White)" if board.turn == chess.WHITE else "Stockfish (Black)"
    return f"Move {board.fullmove_number} — {who} to play"


def confidence_text(conf: float | None) -> str:
    if conf is None:
        return "Jev's confidence: not reported"
    if conf >= 0.75:
        word = "very sure"
    elif conf >= 0.5:
        word = "fairly sure"
    elif conf >= 0.3:
        word = "unsure"
    else:
        word = "guessing"
    return f"Jev was {word} ({conf:.0%} sure)"


def format_json_lines(obj, max_lines: int = 2000) -> list[str]:
    """Pretty-print a JSON-safe object as lines for the detail view."""
    import json

    try:
        text = json.dumps(obj, indent=1, default=str)
    except (TypeError, ValueError):
        text = str(obj)
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"… ({len(lines) - max_lines} more lines)"]
    return lines


def confidence_meter(conf: float | None) -> tuple[float, tuple[int, int, int]]:
    """(fill fraction 0..1, bar color) for the confidence meter. Thresholds match confidence_text."""
    if conf is None:
        return 0.0, (100, 100, 105)
    fraction = max(0.0, min(1.0, conf))
    if conf >= 0.75:
        color = (74, 160, 90)
    elif conf >= 0.5:
        color = (210, 170, 40)
    elif conf >= 0.3:
        color = (220, 130, 40)
    else:
        color = (200, 70, 70)
    return fraction, color
