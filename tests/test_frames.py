import pytest

from jev_chess.frames import Frame, History


def _frame(ply, fen):
    return Frame(ply=ply, fen=fen, parent_fen=None, move_uci="e2e4", move_san="e4", side="white")


def test_push_and_navigate():
    h = History(initial_fen="start")
    assert h.view_fen() == "start"
    for i in range(1, 5):
        h.push(_frame(i, f"fen{i}"))
    assert h.at_tip
    assert h.view_fen() == "fen4"
    assert h.back() == "fen3"
    assert h.back() == "fen2"
    assert h.forward() == "fen3"
    h.forward()
    assert h.at_tip


def test_push_locked_when_not_at_tip():
    h = History(initial_fen="start")
    h.push(_frame(1, "fen1"))
    h.push(_frame(2, "fen2"))
    h.back()
    assert not h.at_tip
    with pytest.raises(RuntimeError):
        h.push(_frame(3, "fen3"))
