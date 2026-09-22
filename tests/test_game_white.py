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
        state={"fen": board.fen()},
        questions={"move": {"instructions": "x", "criteria": {}}},
        response_json={"answers": {"move": {"choice": "e2e4"}}},
    )
    frame = game.play_white_from_distribution(dist, temperature=0.0)
    assert frame.move_uci == "e2e4"
    assert frame.jev_state["fen"] == chess.Board().fen()
    assert frame.jev_response["answers"]["move"]["choice"] == "e2e4"
    # Everything stored must be JSON-serializable for the detail view.
    json.dumps(frame.jev_state)
    json.dumps(frame.jev_questions)
    json.dumps(frame.jev_response)
    game.close()
