# Jev Chess — Feature Plan (v1)

## Goal
Simple bot where **Jev (White)** plays against a **python-chess engine (Black, Stockfish)** with step-through UI, temperature sampling, and full move history.

## Components
1. **Opponent (`chess.engine.SimpleEngine.popen_uci`)**
   - `python-chess` owns all rules: `Board`, `legal_moves`, `is_game_over`, `fen`, `san`.
   - Black plays via `engine.play(board, Limit(time=0.1))`.
   - Stockfish binary required (apt/brew or explicit path).

2. **Jev mover (`typesafe-sdk`, `TypeSafeClient.system_one`)**
   - Jev is System One: no free-text generation, only `Choice` over supplied options.
   - `state` (JSON object per `concepts/state.md`):
     `{moves_san, movetext, turn, is_check, last_move, board_ascii, legal_moves: [{uci, san, descr}]}`.
     No FEN: Jev gets readable notation instead; each option's `descr` carries
     code-computed consequence flags (capture values, check, castling, landing-square
     danger as attackers vs defenders) and the instructions ask for the move with the
     best overall future given likely replies.
   - `questions = {"move": Choice(instructions=..., criteria={uci: descr})}`.
     Instructions carry full meaning; criteria keys are UCI, values are human-readable (`"Nf3: Knight g1 to f3"` + capture/check flags).
   - Legal moves ~20-40, under 255-option Choice limit.
   - Read `choice`, `probabilities`, `confidence`, `usage`. Validate chosen UCI is legal; fallback to greedy/top-prob legal move on failure.
   - `TYPESAFE_API_KEY` from env only, never hardcoded.

3. **Temperature sampling (single function covers all modes)**
   - Input: `probs: dict[uci, p]`, `temperature T`, `seed`.
   - `T=0` → argmax (greedy). `T=1` → sample raw distribution. `T<1` sharper, `T>1` flatter.
   - Formula: `p_T(i) ∝ p_i^(1/T)`, renormalize; `p=0` stays 0.
   - Optional `top_k`/`top_p` pre-filter (deferred if not needed in v1).
   - Deterministic with seeded `random.Random`.

4. **Step-at-a-time UI (terminal v1, pygame later)**
   - No auto-play. States: `awaiting-step → play-one-ply → render → awaiting-step`.
   - Commands: `n/Enter` next, `b` back, `f` forward, `t` set temperature, `q` quit.
   - Stats per Jev ply: move `uci/san`, `confidence`, latency ms, input/output tokens, top-5 probs with bars, `fen`, check status.
   - Engine plies show move + time + eval if available.

5. **Frame history (back/forth, forking deferred)**
   - `frames: list[Frame]` + `cursor`. `Frame = {ply, fen, move_uci, move_san, side, jev_{probs,choice,confidence,usage,latency,temperature} | engine_{move,time}, is_check, result}`.
   - Push one frame per ply. Back/forward renders from `frames[cursor]` (read-only view).
   - v1 rule: if `cursor < tip`, Next is locked — must go to tip to continue (prevents accidental branches).
   - Forking deferred: future tree `{id, parent_id}` + branch selector. Keep `parent_fen` in Frame for migration.

## Acceptance Criteria (v1 status 2026-09-22)
- [x] `uv run python -m jev_chess.cli --help` works; deps via `uv add chess typesafe-sdk`.
- [x] Engine path verified with Stockfish 17.1 (`e4 → e7e5` @ 0.1s). Full Jev-vs-engine game needs `TYPESAFE_API_KEY` + Stockfish at runtime.
- [x] Without Stockfish, `EngineMissing` with install/`--engine-path` message (no traceback).
- [x] Without `TYPESAFE_API_KEY`, friendly error; key never logged (grep clean).
- [x] Sampling tests: T=0 argmax, T=1 identity, T=10 flattens, T=0.1 sharpens, zeros stay zero, seeded determinism (`8 passed`).
- [x] Step UI: Enter=one ply, `b`/`f` cursor navigate + re-render, Next locked when `cursor < tip`.
- [x] Stats per Jev ply: choice, confidence, top-5 bars, tokens, latency, fen.
- [x] History test: push/navigate/lock covered in `test_frames.py`.
- [x] Invalid Jev UCI falls back to argmax legal, game continues.
- [x] `pytest` passes; `py_compile` clean.

## Non-goals (v1)
- Pygame board, eval bar, hints, undo-takeback vs engine, PGN export, forking/tree branches, ELO strength.

## File layout
- `FEATURE_PLAN.md` (this file), `pyproject.toml`, `src/jev_chess/{__init__,sampling,frames,jev_player,game,cli,ui_pygame,board_viz}.py`, `tests/test_sampling.py`, `tests/test_frames.py`, `tests/test_board_viz.py`.

## GUI (pygame, v1 status 2026-09-22)
- `uv run python -m jev_chess.ui_pygame` (or `jev-chess-gui`). Terminal `cli.py` kept as fallback.
- Existing packages checked: `chess.svg` draws arrows but only static SVG (no per-move width/alpha control in a live window); `python-chess-gui` (PyPI) is a standalone app, not an embeddable probability-arrow widget. So arrows are custom-drawn in pygame; no extra dependency beyond `pygame`.
- Board left (unicode pieces, last-move + check highlights, coordinates); panel right with plain-language turn/result, Back/Next/Forward, autoplay `Off|On|Stockfish only` + speed (0.5/1/2s), temperature slider 0–2 + Solid/Balanced/Adventurous presets, arrows on/off + top 3/5/8, message line, Jev stats (confidence words, ms, tokens, daring used), scrollable move list.
- Probability arrows: shown BEFORE the move. Jev distribution auto-fetched right after Stockfish moves (and at game start), one API call cached per-FEN; Space locks in by sampling the cache with current daring (no second call). History frames keep stored distributions for hindsight.
- Move list: one line per move; click expands to full Jev query (state + questions) and response (answers + usage) as two JSON blocks (Stockfish moves show engine detail). X/header collapses; wheel scrolls detail. Frames store all three JSON objects.
- Verified headless (dummy SDL): render + live Jev e4 (68%) / engine e5 + arrow render + clean quit; 13 tests pass.
