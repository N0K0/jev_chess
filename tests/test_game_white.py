import json

import chess

from jev_chess.game import Game
from jev_chess.jev_player import JevDistribution


def test_white_lockin_from_cached_distribution_needs_no_api():
    game = Game(engine_path="/nonexistent-stockfish")  # white needs no engine
    board = chess.Board()
    dist = JevDistribution(
        probs={m.uci(): (0.9 if m.uci() == "e2e4" else 0.1 / 19) for m in board.legal_moves},
        confidence=0.8,
        input_tokens=10,
        output_tokens=5,
        latency_ms=1.0,
        state={"moves_san": [], "movetext": ""},
        questions={"move": {"instructions": "x", "criteria": {}}},
        response_json={"answers": {"move": {"choice": "e2e4"}}},
    )
    frame = game.play_white_from_distribution(dist, temperature=0.0)
    assert frame.move_uci == "e2e4"
    assert frame.jev_state["moves_san"] == []
    assert frame.jev_state["movetext"] == ""
    assert "fen" not in frame.jev_state
    assert frame.jev_response["answers"]["move"]["choice"] == "e2e4"
    # Everything stored must be JSON-serializable for the detail view.
    json.dumps(frame.jev_state)
    json.dumps(frame.jev_questions)
    json.dumps(frame.jev_response)
    game.close()


def test_move_notation():
    import chess

    from jev_chess.jev_player import build_state, move_notation

    board = chess.Board()
    sans, text = move_notation(board)
    assert sans == [] and text == ""
    for san in ("e4", "e5", "Nf3"):
        board.push_san(san)
    sans, text = move_notation(board)
    assert sans == ["e4", "e5", "Nf3"]
    assert text == "1. e4 e5 2. Nf3"
    state = build_state(board)
    assert state["moves_san"] == ["e4", "e5", "Nf3"]
    assert state["movetext"] == "1. e4 e5 2. Nf3"
    assert "fen" not in state
