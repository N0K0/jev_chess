"""Jev mover: encode board as state, ask Choice over legal moves."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import chess


MOVE_INSTRUCTIONS = (
    "Select the move that leads to the best overall future for the side to move, "
    "not just the best-looking move right now. For each option, weigh what happens "
    "after it: the resulting position, the opponent's likely replies, and whether "
    "the landing square is under attack (flagged per option). Prefer moves that keep "
    "the king safe afterwards, develop pieces, control the center, win material safely, "
    "and create threats the opponent must answer. Avoid moves whose only merit is "
    "immediate but allow a strong reply, and avoid hanging pieces on undefended squares. "
    "Answer with exactly one of the listed options."
)

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def describe_move(board: chess.Board, move: chess.Move) -> str:
    san = board.san(move)
    piece = board.piece_at(move.from_square)
    name = piece.symbol().upper() if piece else "?"
    descr = f"{san}: {name} {chess.square_name(move.from_square)} to {chess.square_name(move.to_square)}"
    if board.is_capture(move):
        if board.is_en_passant(move):
            descr += ", captures en passant (1 pt)"
        else:
            captured = board.piece_at(move.to_square)
            value = PIECE_VALUES.get(captured.piece_type, 0) if captured else 0
            label = chess.piece_name(captured.piece_type) if captured else "piece"
            descr += f", captures {label} ({value} pt)"
    if move.promotion:
        descr += f", promote to {chess.piece_name(move.promotion)}"
    if board.gives_check(move):
        descr += ", gives check"
    if board.is_castling(move):
        descr += ", castles (king to safety)"
    if board.is_en_passant(move):
        descr += ", en passant"
    enemy = not board.turn
    attackers = len(board.attackers(enemy, move.to_square))
    defenders = len(board.attackers(board.turn, move.to_square))
    if attackers == 0:
        descr += ", lands on a safe square"
    elif defenders == 0:
        descr += f", lands under attack by {attackers} (undefended: could hang)"
    else:
        descr += f", lands under attack by {attackers} (defended by {defenders})"
    return descr


def move_notation(board: chess.Board) -> tuple[list[str], str]:
    """SAN list and movetext (e.g. '1. e4 e5') for all moves played so far."""
    replay = chess.Board()
    sans: list[str] = []
    for m in board.move_stack:
        sans.append(replay.san(m))
        replay.push(m)
    parts = []
    for i in range(0, len(sans), 2):
        n = i // 2 + 1
        white, black = sans[i], sans[i + 1] if i + 1 < len(sans) else ""
        parts.append(f"{n}. {white} {black}".rstrip())
    return sans, " ".join(parts)


def build_state(board: chess.Board) -> dict:
    legal = list(board.legal_moves)
    moves_san, movetext = move_notation(board)
    return {
        "moves_san": moves_san,
        "movetext": movetext,
        "turn": "white" if board.turn == chess.WHITE else "black",
        "is_check": board.is_check(),
        "last_move": board.peek().uci() if board.move_stack else None,
        "board_ascii": str(board),
        "legal_moves": [
            {"uci": m.uci(), "san": board.san(m), "descr": describe_move(board, m)}
            for m in legal
        ],
    }


def build_criteria(board: chess.Board) -> dict[str, str]:
    return {m.uci(): describe_move(board, m) for m in board.legal_moves}


@dataclass
class JevDistribution:
    """Raw Jev answer: full distribution, no move picked yet."""

    probs: dict[str, float]
    confidence: float | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    # Full query/response kept for the expandable detail view (JSON-safe).
    state: dict | None = None
    questions: dict | None = None
    response_json: dict | None = None


@dataclass
class JevResult:
    uci: str
    probs: dict[str, float]
    confidence: float | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float


def fetch_distribution(board: chess.Board) -> JevDistribution:
    """Ask Jev for its move distribution. One API call, no sampling."""
    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        raise RuntimeError("TYPESAFE_API_KEY is not set. Export it before playing Jev moves.")

    criteria = build_criteria(board)
    if not criteria:
        raise RuntimeError("No legal moves available.")

    # Import here so unit tests / engine-only runs don't require the SDK.
    try:
        from typesafe_sdk import Choice, TypeSafeClient
    except ImportError as e:
        raise RuntimeError("typesafe-sdk is not installed. Run `uv add typesafe-sdk`.") from e

    state = build_state(board)
    questions = {"move": {"instructions": MOVE_INSTRUCTIONS, "criteria": criteria}}
    start = time.perf_counter()
    with TypeSafeClient() as client:
        response = client.system_one(
            state=state,
            questions={"move": Choice(instructions=MOVE_INSTRUCTIONS, criteria=criteria)},
        )
    latency_ms = (time.perf_counter() - start) * 1000.0

    answer = response.answers["move"] if isinstance(response.answers, dict) else response.choices["move"]
    legal_uci = set(criteria)
    probs = {k: float(v) for k, v in dict(answer.probabilities).items() if k in legal_uci}

    usage = getattr(response, "usage", None)
    in_tok = getattr(usage, "input_tokens", None) if usage else None
    out_tok = getattr(usage, "output_tokens", None) if usage else None
    if in_tok is None and isinstance(usage, dict):
        in_tok = usage.get("input_tokens")
        out_tok = usage.get("output_tokens")

    response_json = {
        "model": getattr(response, "model", None),
        "answers": {
            "move": {
                "type": "choice",
                "choice": getattr(answer, "choice", None),
                "confidence": getattr(answer, "confidence", None),
                "probabilities": {k: float(v) for k, v in dict(answer.probabilities).items()},
            }
        },
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }

    return JevDistribution(
        probs=probs,
        confidence=getattr(answer, "confidence", None),
        input_tokens=in_tok,
        output_tokens=out_tok,
        latency_ms=latency_ms,
        state=state,
        questions=questions,
        response_json=response_json,
    )


def resolve_uci(probs: dict[str, float], legal_uci: set[str], temperature: float, seed: int | None) -> str:
    """Sample a UCI from probs; fall back to argmax legal on mismatch."""
    from jev_chess.sampling import sample_move

    uci = sample_move(probs, temperature=temperature, seed=seed)
    if uci not in legal_uci:
        uci = max(probs, key=lambda k: (probs[k], k)) if probs else next(iter(legal_uci))
        if uci not in legal_uci:
            uci = sorted(legal_uci)[0]
    return uci


def choose_move(board: chess.Board, temperature: float = 0.0, seed: int | None = None) -> JevResult:
    """Call Jev and sample a move. Raises RuntimeError with friendly message on config errors."""
    dist = fetch_distribution(board)
    legal_uci = {m.uci() for m in board.legal_moves}
    uci = resolve_uci(dist.probs, legal_uci, temperature, seed)
    return JevResult(
        uci=uci,
        probs=dist.probs,
        confidence=dist.confidence,
        input_tokens=dist.input_tokens,
        output_tokens=dist.output_tokens,
        latency_ms=dist.latency_ms,
    )
