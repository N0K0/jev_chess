"""Step-through terminal UI with Jev stats."""

from __future__ import annotations

import argparse

import chess
from dotenv import load_dotenv

from jev_chess.game import EngineMissing, Game

load_dotenv()


def top_lines(probs: dict[str, float], n: int = 5) -> list[str]:
    ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:n]
    lines = []
    for uci, p in ranked:
        bar = "#" * int(round(p * 20))
        lines.append(f"  {uci:6s} {p:6.2%} {bar}")
    return lines


def render(board: chess.Board, note: str = "") -> None:
    from jev_chess.jev_player import move_notation

    print()
    print(board)
    _, movetext = move_notation(board)
    print(f"Moves: {movetext or '(none yet)'}")
    if board.is_check():
        print("Check!")
    if note:
        print(note)


def main() -> None:
    ap = argparse.ArgumentParser(description="Jev (White) vs Stockfish (Black), step-through.")
    ap.add_argument("--engine-path", default=None)
    ap.add_argument("--engine-time", type=float, default=0.1)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    try:
        game = Game(engine_path=args.engine_path, engine_time=args.engine_time)
    except EngineMissing as e:
        print(f"Error: {e}")
        raise SystemExit(2)

    temperature = args.temperature
    print("Jev (White) vs Stockfish (Black). Enter=b/next, b=back, f=forward, t=set temp, q=quit.")
    print(f"Temperature={temperature} (0=greedy, 1=sample raw, >1 flatter).")
    render(game.board, f"Ply 0/{len(game.history.frames)} tip.")

    try:
        while True:
            if game.board.is_game_over():
                print(f"Game over: {game.board.result()}")
            cmd = input(f"[ply {game.history.cursor + 1}/{len(game.history.frames)} T={temperature}] (n/b/f/t/q): ").strip().lower()
            if cmd in ("", "n", "next"):
                if not game.history.at_tip:
                    print("Viewing history — press f to return to tip before stepping.")
                    continue
                try:
                    frame = game.step(temperature=temperature, seed=args.seed)
                except RuntimeError as e:
                    print(f"Cannot step: {e}")
                    continue
                except Exception as e:
                    print(f"Move failed: {e}")
                    continue
                view = chess.Board(frame.fen)
                if frame.side == "white":
                    print(f"Jev played {frame.move_san} ({frame.move_uci}) conf={frame.jev_confidence} "
                          f"lat={frame.latency_ms:.0f}ms tok={frame.input_tokens}/{frame.output_tokens}")
                    for line in top_lines(frame.jev_probs):
                        print(line)
                else:
                    print(f"Engine played {frame.move_san} ({frame.move_uci}) in {frame.engine_time_s:.2f}s")
                render(view)
            elif cmd == "b":
                fen = game.history.back()
                render(chess.Board(fen), f"Viewing history {game.history.cursor + 1}/{len(game.history.frames)}.")
            elif cmd == "f":
                fen = game.history.forward()
                render(chess.Board(fen), f"Viewing history {game.history.cursor + 1}/{len(game.history.frames)}.")
            elif cmd.startswith("t"):
                parts = cmd.split()
                val = parts[1] if len(parts) > 1 else input("temperature: ").strip()
                try:
                    temperature = float(val)
                    assert temperature >= 0
                except Exception:
                    print("Temperature must be a number >= 0.")
            elif cmd in ("q", "quit"):
                break
            else:
                print("Unknown: n/b/f/t/q.")
    finally:
        game.close()


if __name__ == "__main__":
    main()
