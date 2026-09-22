import chess

from jev_chess.jev_player import MOVE_INSTRUCTIONS, build_criteria


def test_instructions_ask_for_best_future():
    assert "future" in MOVE_INSTRUCTIONS
    assert "likely replies" in MOVE_INSTRUCTIONS


def test_safe_landing_flagged():
    criteria = build_criteria(chess.Board())
    assert criteria["e2e4"].endswith("lands on a safe square")


def test_capture_value_and_contested_square():
    board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    descr = build_criteria(board)["e4d5"]
    assert "captures pawn (1 pt)" in descr
    assert "lands under attack by 1 (defended by 1)" in descr


def test_check_and_hanging_flags():
    board = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/2B1P3/8/PPPP1PPP/RNBQK1NR w KQkq - 0 2")
    descr = build_criteria(board)["c4f7"]
    assert "captures pawn (1 pt)" in descr
    assert "gives check" in descr
    assert "under attack" in descr
