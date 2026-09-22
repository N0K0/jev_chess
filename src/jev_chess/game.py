"""Game orchestration: Jev (White) vs Stockfish (Black), one ply per step."""

from __future__ import annotations

import shutil
import time

import chess
import chess.engine

from jev_chess.frames import Frame, History


def _engine_info_json(result: chess.engine.PlayResult, elapsed: float) -> dict:
    """JSON-safe engine detail for the expandable view."""
    info = {"move": result.move.uci() if result.move else None, "elapsed_s": round(elapsed, 3)}
    try:
        raw = dict(result.info or {})
    except Exception:
        return info
    score = raw.get("score")
    if score is not None:
        try:
            info["score_cp_white"] = score.white().score()
            info["mate_white"] = score.white().mate()
        except Exception:
            info["score"] = str(score)
    pv = raw.get("pv")
    if pv:
        try:
            info["pv"] = [m.uci() for m in pv][:10]
        except Exception:
            pass
    for key in ("depth", "seldepth", "nodes", "nps", "time"):
        if raw.get(key) is not None:
            try:
                info[key] = float(raw[key])
            except (TypeError, ValueError):
                pass
    return info


class EngineMissing(RuntimeError):
    pass


def find_engine(path: str | None) -> str:
    if path:
        return path
    found = shutil.which("stockfish")
    if found:
        return found
    raise EngineMissing(
        "Stockfish not found. Install it (apt install stockfish / brew install stockfish) "
        "or pass --engine-path /path/to/stockfish."
    )


class Game:
    def __init__(self, engine_path: str | None = None, engine_time: float = 0.1) -> None:
        self.board = chess.Board()
        self.history = History(initial_fen=self.board.fen())
        self.engine_path = find_engine(engine_path)
        self.engine_time = engine_time
        self._engine: chess.engine.SimpleEngine | None = None

    def engine(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            try:
                self._engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
            except Exception as e:
                raise EngineMissing(f"Could not start Stockfish at {self.engine_path}: {e}") from e
        return self._engine

    def close(self) -> None:
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception:
                pass
            self._engine = None

    def play_white_from_distribution(
        self,
        dist,  # JevDistribution: cached ideas, sampled here so temperature applies at lock-in
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> Frame:
        """Lock in White's move from a previously fetched distribution."""
        from jev_chess.jev_player import resolve_uci

        if self.board.is_game_over():
            raise RuntimeError(f"Game over: {self.board.result()}")
        if not self.history.at_tip:
            raise RuntimeError("Viewing history: go forward to tip before stepping.")
        if self.board.turn != chess.WHITE:
            raise RuntimeError("Not Jev's turn.")

        parent_fen = self.board.fen()
        legal_uci = {m.uci() for m in self.board.legal_moves}
        uci = resolve_uci(dist.probs, legal_uci, temperature, seed)
        move = chess.Move.from_uci(uci)
        san = self.board.san(move)
        self.board.push(move)
        frame = Frame(
            ply=len(self.board.move_stack),
            fen=self.board.fen(),
            parent_fen=parent_fen,
            move_uci=uci,
            move_san=san,
            side="white",
            is_check=self.board.is_check(),
            result=self.board.result() if self.board.is_game_over() else None,
            jev_choice=uci,
            jev_probs=dist.probs,
            jev_confidence=dist.confidence,
            jev_temperature=temperature,
            input_tokens=dist.input_tokens,
            output_tokens=dist.output_tokens,
            latency_ms=dist.latency_ms,
            jev_state=dist.state or {},
            jev_questions=dist.questions or {},
            jev_response=dist.response_json or {},
        )
        self.history.push(frame)
        return frame

    def step(self, temperature: float = 0.0, seed: int | None = None) -> Frame:
        """Play exactly one ply at the tip. Raises if game over or not at tip."""
        from jev_chess.jev_player import fetch_distribution

        if self.board.is_game_over():
            raise RuntimeError(f"Game over: {self.board.result()}")
        if not self.history.at_tip:
            raise RuntimeError("Viewing history: go forward to tip before stepping.")

        parent_fen = self.board.fen()
        if self.board.turn == chess.WHITE:
            dist = fetch_distribution(self.board)
            return self.play_white_from_distribution(dist, temperature=temperature, seed=seed)
        else:
            start = time.perf_counter()
            result = self.engine().play(self.board, chess.engine.Limit(time=self.engine_time))
            elapsed = time.perf_counter() - start
            if result.move is None:
                raise RuntimeError("Engine returned no move.")
            san = self.board.san(result.move)
            uci = result.move.uci()
            self.board.push(result.move)
            frame = Frame(
                ply=len(self.board.move_stack),
                fen=self.board.fen(),
                parent_fen=parent_fen,
                move_uci=uci,
                move_san=san,
                side="black",
                is_check=self.board.is_check(),
                result=self.board.result() if self.board.is_game_over() else None,
                engine_time_s=elapsed,
                engine_info=_engine_info_json(result, elapsed),
            )
        self.history.push(frame)
        return frame
