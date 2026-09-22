"""Pygame UI: Jev (White) vs Stockfish (Black), step-through with probability arrows.

Run: uv run python -m jev_chess.ui_pygame [--temperature 0] [--autoplay off|on|opponent]
"""

from __future__ import annotations

import argparse
import math
import sys

import chess
import pygame
from dotenv import load_dotenv

from jev_chess.board_viz import (
    AUTOPLAY_MODES,
    confidence_text,
    format_json_lines,
    preview_usable,
    probs_to_arrows,
    arrow_style,
    should_auto_step,
    side_to_move_text,
)
from jev_chess.game import EngineMissing, Game

load_dotenv()

BOARD_PX = 720
SQ = BOARD_PX // 8
PANEL_X = BOARD_PX + 20
WIN_W = PANEL_X + 380
WIN_H = BOARD_PX + 20

LIGHT = (240, 217, 181)
DARK = (181, 136, 99)
LASTMOVE = (247, 231, 105)
CHECK_RED = (235, 87, 87)
BG = (30, 30, 34)
PANEL_BG = (43, 43, 48)
TEXT = (235, 235, 235)
DIM = (170, 170, 175)
GREEN = (46, 160, 80)
AMBER = (215, 140, 20)
BTN = (62, 62, 70)
BTN_HOV = (80, 80, 92)
ACCENT = (70, 130, 200)

GLYPHS = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
}
TEMP_PRESETS = [("Solid", 0.0), ("Balanced", 1.0), ("Adventurous", 1.5)]
SPEEDS = [0.5, 1.0, 2.0]
TOP_KS: list[int | None] = [3, 5, 8, None]  # None = show all moves


def topk_label(top_k: int | None) -> str:
    return "Show all" if top_k is None else f"Show top {top_k}"


def sq_xy(sq: int) -> tuple[int, int]:
    f, r = chess.square_file(sq), chess.square_rank(sq)
    return 10 + f * SQ, 10 + (7 - r) * SQ


def sq_center(sq: int) -> tuple[float, float]:
    x, y = sq_xy(sq)
    return x + SQ / 2, y + SQ / 2


class Button:
    def __init__(self, rect: pygame.Rect, label: str, tag: str):
        self.rect = rect
        self.label = label
        self.tag = tag
        self.disabled = False

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, active: bool = False):
        color = BTN_HOV if self.hovered() else BTN
        if active:
            color = ACCENT
        if self.disabled:
            color = (45, 45, 50)
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        fg = DIM if self.disabled else TEXT
        img = font.render(self.label, True, fg)
        screen.blit(img, img.get_rect(center=self.rect.center))

    def hovered(self) -> bool:
        return self.rect.collidepoint(pygame.mouse.get_pos())


def wrap(text: str, font: pygame.font.Font, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.size(trial)[0] <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


class App:
    def __init__(self, args: argparse.Namespace):
        pygame.init()
        pygame.display.set_caption("Jev Chess — Jev (White) vs Stockfish (Black)")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("dejavusans", 18)
        self.small = pygame.font.SysFont("dejavusans", 14)
        self.big = pygame.font.SysFont("dejavusans", 64)
        self.piece_font = pygame.font.SysFont("dejavusans", 58)

        try:
            self.game = Game(engine_path=args.engine_path, engine_time=args.engine_time)
        except EngineMissing as e:
            print(f"Error: {e}")
            pygame.quit()
            sys.exit(2)
        self.temperature = args.temperature
        self.seed = args.seed
        self.autoplay = args.autoplay if args.autoplay in AUTOPLAY_MODES else "off"
        self.speed_idx = 1
        self.show_arrows = True
        self.top_k_idx = 1
        self.move_scroll = 0
        self.expanded_ply: int | None = None
        self.detail_scroll = 0
        self.detail_lines: list[str] = []
        self.move_line_rects: list = []
        self.detail_head_rect: pygame.Rect | None = None
        self.quit_rect: pygame.Rect | None = None
        self.quit_requested = False
        self.ask_rect: pygame.Rect | None = None
        self.message = "Asking Jev for its first ideas…"
        self.accum_ms = 0.0
        self.temp_drag = False
        # Preview cache: Jev's distribution for an exact position, fetched
        # automatically after Stockfish moves (and at game start). Space locks it in.
        self.preview_dist = None
        self.preview_fen: str | None = None
        self.fetch_failed_fen: str | None = None

        y = 10
        self.btn_back = Button(pygame.Rect(PANEL_X, y, 110, 34), "◀ Back", "back")
        self.btn_next = Button(pygame.Rect(PANEL_X + 120, y, 130, 34), "Next move ▶", "next")
        self.btn_fwd = Button(pygame.Rect(PANEL_X + 260, y, 100, 34), "Fwd ▶", "fwd")
        self.mode_rects = {
            m: pygame.Rect(PANEL_X + i * 118, 0, 112, 30) for i, m in enumerate(AUTOPLAY_MODES)
        }
        self.speed_rect = pygame.Rect(PANEL_X + 240, 0, 120, 30)
        self.preset_rects = [pygame.Rect(PANEL_X + i * 118, 0, 112, 28) for i in range(3)]
        self.slider_rect = pygame.Rect(PANEL_X, 0, 360, 26)
        self.arrow_rect = pygame.Rect(PANEL_X, 0, 200, 28)
        self.topk_rect = pygame.Rect(PANEL_X + 210, 0, 150, 28)

    # ---- actions ----
    def has_preview(self) -> bool:
        return preview_usable(
            self.preview_fen,
            self.game.board.fen(),
            self.game.board.turn == chess.WHITE,
            self.game.history.at_tip,
            self.game.board.is_game_over(),
        )

    def do_fetch(self):
        """Ask Jev for its ideas on the current position (one API call)."""
        from jev_chess.jev_player import fetch_distribution

        fen = self.game.board.fen()
        self.message = "Asking Jev what it's thinking…"
        pygame.display.flip()
        try:
            self.preview_dist = fetch_distribution(self.game.board)
        except Exception as e:
            self.preview_dist = None
            self.preview_fen = None
            self.fetch_failed_fen = fen
            self.message = f"Couldn't reach Jev ({type(e).__name__}): {e}"
            self.autoplay = "off"
            return
        self.preview_fen = fen
        self.fetch_failed_fen = None
        top = sorted(self.preview_dist.probs.items(), key=lambda kv: -kv[1])[0][0]
        self.message = (
            f"Jev is weighing up its move (favourite so far: {top}). "
            "Press Space to lock it in."
        )
        self.accum_ms = 0.0

    def do_lockin(self):
        """Sample the cached preview with the current daring and play it."""
        try:
            frame = self.game.play_white_from_distribution(
                self.preview_dist, temperature=self.temperature, seed=self.seed
            )
        except RuntimeError as e:
            self.message = str(e)
            self.autoplay = "off"
            return
        self.message = (
            f"Jev locked in {frame.move_san}. {confidence_text(frame.jev_confidence)}."
        )
        self.accum_ms = 0.0

    def do_engine(self):
        try:
            frame = self.game.step(temperature=self.temperature, seed=self.seed)
        except RuntimeError as e:
            self.message = str(e)
            self.autoplay = "off"
            return
        except Exception as e:  # engine / API failure: pause, don't spin
            self.message = f"Move failed ({type(e).__name__}): {e}"
            self.autoplay = "off"
            return
        self.message = (
            f"Stockfish replied {frame.move_san} "
            f"(thought for {frame.engine_time_s:.1f}s). Asking Jev…"
        )
        self.accum_ms = 0.0

    def advance(self):
        """One user/auto step: lock in Jev, fetch if needed, or play Stockfish."""
        if self.game.board.is_game_over():
            self.message = f"Game over: {self.game.board.result()}"
            self.autoplay = "off"
            return
        if not self.game.history.at_tip:
            self.message = "Viewing history — go to the latest to keep playing."
            return
        if self.game.board.turn == chess.WHITE:
            if self.has_preview():
                self.do_lockin()
            else:
                self.fetch_failed_fen = None  # retry on explicit press
                self.do_fetch()
        else:
            self.do_engine()

    def viewed_board(self) -> chess.Board:
        cur = self.game.history.current()
        if cur is None:
            return chess.Board(self.game.history.initial_fen)
        return chess.Board(cur.fen)

    def viewed_is_tip(self, board: chess.Board) -> bool:
        return self.game.history.at_tip and board.fen() == self.game.board.fen()

    # ---- drawing ----
    def draw_board(self, board: chess.Board, last_uci: str | None):
        for r in range(8):
            for f in range(8):
                x, y = 10 + f * SQ, 10 + r * SQ
                pygame.draw.rect(
                    self.screen, LIGHT if (r + f) % 2 == 0 else DARK, (x, y, SQ, SQ)
                )
        if last_uci:
            try:
                m = chess.Move.from_uci(last_uci)
                for sq in (m.from_square, m.to_square):
                    x, y = sq_xy(sq)
                    s = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                    s.fill((*LASTMOVE, 130))
                    self.screen.blit(s, (x, y))
            except ValueError:
                pass
        if board.is_check():
            king = board.king(board.turn)
            if king is not None:
                x, y = sq_xy(king)
                s = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                s.fill((*CHECK_RED, 150))
                self.screen.blit(s, (x, y))
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if not piece:
                continue
            x, y = sq_xy(sq)
            glyph = GLYPHS[piece.symbol()]
            is_white = piece.color == chess.WHITE
            main, edge = ((255, 255, 255), (20, 20, 20)) if is_white else ((20, 20, 20), (235, 235, 235))
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                img = self.piece_font.render(glyph, True, edge)
                self.screen.blit(img, img.get_rect(center=(x + SQ / 2 + dx, y + SQ / 2 + dy)))
            img = self.piece_font.render(glyph, True, main)
            self.screen.blit(img, img.get_rect(center=(x + SQ / 2, y + SQ / 2)))
        # coordinates
        for i in range(8):
            c = self.small.render(chr(97 + i), True, DIM)
            self.screen.blit(c, (10 + i * SQ + 4, 10 + BOARD_PX - 20))
            c = self.small.render(str(8 - i), True, DIM)
            self.screen.blit(c, (12, 12 + i * SQ + 4))

    def draw_arrows(self, probs: dict[str, float]):
        top_k = TOP_KS[self.top_k_idx]
        arrows = probs_to_arrows(probs, top_k=top_k, min_p=0.0 if top_k is None else 0.01)
        if not arrows:
            return
        overlay = pygame.Surface((BOARD_PX + 20, BOARD_PX + 20), pygame.SRCALPHA)
        max_p = arrows[0].prob
        for a in arrows:
            x1, y1 = sq_center(a.from_square)
            x2, y2 = sq_center(a.to_square)
            dx, dy = x2 - x1, y2 - y1
            dist = math.hypot(dx, dy) or 1.0
            ux, uy = dx / dist, dy / dist
            sx, sy = x1 + ux * 30, y1 + uy * 30
            ex, ey = x2 - ux * 36, y2 - uy * 36
            width, alpha = arrow_style(a.prob, max_p)
            rgb = (34, 150, 75) if a.rank == 0 else (220, 145, 25)
            pygame.draw.line(overlay, (*rgb, alpha), (sx, sy), (ex, ey), width)
            # head triangle
            hl, hw = 26, 11 + width // 2
            px, py = -uy, ux
            pts = [(x2 - ux * 8, y2 - uy * 8),
                   (ex + px * hw, ey + py * hw),
                   (ex - px * hw, ey - py * hw)]
            pygame.draw.polygon(overlay, (*rgb, min(255, alpha + 20)), pts)
            label = self.small.render(f"{a.prob:.0%}", True, (255, 255, 255))
            bg = pygame.Surface((label.get_width() + 8, label.get_height() + 4), pygame.SRCALPHA)
            bg.fill((20, 20, 20, 200))
            lx, ly = x2 + 10, y2 - 24
            overlay.blit(bg, (lx, ly))
            overlay.blit(label, (lx + 4, ly + 2))
        self.screen.blit(overlay, (0, 0))

    def draw_panel(self, board: chess.Board):
        pygame.draw.rect(self.screen, PANEL_BG, (PANEL_X - 10, 0, 390, WIN_H))
        y = 56
        game_over = board.is_game_over()
        for line in wrap(side_to_move_text(board, game_over), self.font, 360):
            self.screen.blit(self.font.render(line, True, TEXT), (PANEL_X, y))
            y += 24
        cur = self.game.history.current()
        pos = f"Showing move {self.game.history.cursor + 1} of {len(self.game.history.frames)}."
        if not self.game.history.at_tip:
            pos += " Go to the latest to keep playing."
        for line in wrap(pos, self.small, 360):
            self.screen.blit(self.small.render(line, True, DIM), (PANEL_X, y))
            y += 20
        y += 6
        # autoplay segmented
        self.screen.blit(self.small.render("Auto-play:", True, DIM), (PANEL_X, y))
        y += 20
        names = {"off": "Off", "on": "On", "opponent": "Stockfish only"}
        for i, m in enumerate(AUTOPLAY_MODES):
            r = pygame.Rect(PANEL_X + i * 118, y, 112, 30)
            self.mode_rects[m] = r
            active = self.autoplay == m
            pygame.draw.rect(self.screen, ACCENT if active else BTN, r, border_radius=6)
            img = self.small.render(names[m], True, TEXT)
            self.screen.blit(img, img.get_rect(center=r.center))
        self.speed_rect = pygame.Rect(PANEL_X + 240, y + 36, 120, 28)
        y += 36
        self.screen.blit(self.small.render("Speed:", True, DIM), (PANEL_X, y + 4))
        pygame.draw.rect(self.screen, BTN, self.speed_rect, border_radius=6)
        img = self.small.render(f"{SPEEDS[self.speed_idx]}s / move", True, TEXT)
        self.screen.blit(img, img.get_rect(center=self.speed_rect.center))
        y += 36
        # temperature
        self.screen.blit(self.small.render("Jev daring (temperature):", True, DIM), (PANEL_X, y))
        y += 20
        for i, (name, _) in enumerate(TEMP_PRESETS):
            r = pygame.Rect(PANEL_X + i * 118, y, 112, 28)
            self.preset_rects[i] = r
            pygame.draw.rect(self.screen, BTN, r, border_radius=6)
            img = self.small.render(name, True, TEXT)
            self.screen.blit(img, img.get_rect(center=r.center))
        y += 34
        self.slider_rect = pygame.Rect(PANEL_X, y, 300, 26)
        pygame.draw.rect(self.screen, BTN, self.slider_rect, border_radius=6)
        kx = self.slider_rect.x + (self.temperature / 2.0) * self.slider_rect.w
        pygame.draw.circle(self.screen, ACCENT, (int(kx), self.slider_rect.centery), 11)
        img = self.small.render(f"{self.temperature:.1f}", True, TEXT)
        self.screen.blit(img, (self.slider_rect.right + 10, y + 4))
        y += 30
        for line in wrap("0 always takes Jev's favourite; 1 rolls the dice fairly; higher = more surprises.", self.small, 360):
            self.screen.blit(self.small.render(line, True, DIM), (PANEL_X, y))
            y += 18
        # arrows
        self.arrow_rect = pygame.Rect(PANEL_X, y, 200, 28)
        pygame.draw.rect(self.screen, ACCENT if self.show_arrows else BTN, self.arrow_rect, border_radius=6)
        img = self.small.render(f"Arrows: {'on' if self.show_arrows else 'off'}", True, TEXT)
        self.screen.blit(img, img.get_rect(center=self.arrow_rect.center))
        self.topk_rect = pygame.Rect(PANEL_X + 210, y, 150, 28)
        pygame.draw.rect(self.screen, BTN, self.topk_rect, border_radius=6)
        img = self.small.render(topk_label(TOP_KS[self.top_k_idx]), True, TEXT)
        self.screen.blit(img, img.get_rect(center=self.topk_rect.center))
        y += 34
        # message + stats
        for line in wrap(self.message, self.font, 360):
            self.screen.blit(self.font.render(line, True, (255, 220, 150)), (PANEL_X, y))
            y += 24
        if cur is not None and cur.side == "white":
            for line in wrap(
                f"{confidence_text(cur.jev_confidence)}. Took {cur.latency_ms:.0f}ms. "
                f"Used {cur.input_tokens}/{cur.output_tokens} tokens. Daring was {cur.jev_temperature:.1f}. "
                "Arrows show what Jev was weighing up before this move.",
                self.small, 360,
            ):
                self.screen.blit(self.small.render(line, True, DIM), (PANEL_X, y))
                y += 19
        if self.has_preview() and self.viewed_is_tip(board):
            d = self.preview_dist
            for line in wrap(
                f"Jev's ideas for this position: {confidence_text(d.confidence)}. "
                f"Asked in {d.latency_ms:.0f}ms ({d.input_tokens}/{d.output_tokens} tokens). "
                "Daring applies when you lock the move in.",
                self.small, 360,
            ):
                self.screen.blit(self.small.render(line, True, (180, 230, 180)), (PANEL_X, y))
                y += 19
            self.ask_rect = pygame.Rect(PANEL_X, y, 200, 26)
            pygame.draw.rect(self.screen, BTN, self.ask_rect, border_radius=6)
            img = self.small.render("Ask Jev again (R)", True, TEXT)
            self.screen.blit(img, img.get_rect(center=self.ask_rect.center))
            y += 32
        # move list: one line per move; click a line to expand its
        # Jev query + response (or Stockfish detail) as JSON below.
        y += 4
        self.screen.blit(self.small.render("Moves — click one for its query + response:", True, DIM), (PANEL_X, y))
        y += 20
        self.move_line_rects = []
        if self.expanded_ply is None:
            self.detail_head_rect = None
            frames = self.game.history.frames
            start = max(0, min(self.move_scroll, max(0, len(frames) - 8)))
            self.move_scroll = start
            for i in range(start, min(len(frames), start + 8)):
                f = frames[i]
                n = i // 2 + 1
                if f.side == "white":
                    conf = f"{(f.jev_confidence or 0):.0%}" if f.jev_confidence is not None else "?"
                    label = f"▸ {n}. {f.move_san} — Jev ({conf} sure)"
                else:
                    label = f"▸ {n}… {f.move_san} — Stockfish"
                hl = self.game.history.cursor == i
                r = pygame.Rect(PANEL_X, y, 360, 19)
                if hl:
                    pygame.draw.rect(self.screen, (55, 60, 75), r, border_radius=4)
                self.screen.blit(self.small.render(label, True, ACCENT if hl else TEXT), (PANEL_X + 4, y))
                self.move_line_rects.append((r, i))
                y += 19
        else:
            frames = self.game.history.frames
            f = frames[self.expanded_ply] if 0 <= self.expanded_ply < len(frames) else None
            self.detail_head_rect = pygame.Rect(PANEL_X, y, 360, 22)
            pygame.draw.rect(self.screen, (55, 60, 75), self.detail_head_rect, border_radius=4)
            title = f"✕ Move {self.expanded_ply + 1}: {f.move_san}" if f else "✕ Move"
            self.screen.blit(self.small.render(title, True, TEXT), (PANEL_X + 4, y + 2))
            y += 26
            lines: list[str] = []
            if f is not None:
                if f.side == "white":
                    lines.append("── Query sent to Jev ──")
                    lines += format_json_lines({"state": f.jev_state, "questions": f.jev_questions})
                    lines.append("── Response from Jev ──")
                    lines += format_json_lines(f.jev_response)
                else:
                    lines.append("── Stockfish detail ──")
                    lines += format_json_lines(f.engine_info or {"move": f.move_uci})
            self.detail_lines = lines
            per, avail = 17, WIN_H - y - 78
            count = max(1, avail // per)
            max_scroll = max(0, len(lines) - count)
            self.detail_scroll = max(0, min(self.detail_scroll, max_scroll))
            mono = pygame.font.SysFont("dejavusansmono", 12)
            wrapped: list[str] = []
            for line in lines:
                cur = ""
                for w in line.split(" "):
                    trial = f"{cur} {w}".strip()
                    if mono.size(trial)[0] <= 348:
                        cur = trial
                    else:
                        if cur:
                            wrapped.append(cur)
                        cur = w if mono.size(w)[0] <= 348 else w[:60]
                if cur:
                    wrapped.append(cur)
            self.detail_lines = wrapped
            max_scroll = max(0, len(wrapped) - count)
            self.detail_scroll = max(0, min(self.detail_scroll, max_scroll))
            for line in wrapped[self.detail_scroll: self.detail_scroll + count]:
                img = mono.render(line[:90], True, (210, 220, 235))
                self.screen.blit(img, (PANEL_X + 4, y))
                y += per

        # footer: every hotkey as a hint, plus a Quit button
        fy = WIN_H - 64
        pygame.draw.line(self.screen, (70, 70, 78), (PANEL_X - 10, fy - 8), (WIN_W, fy - 8))
        for line in (
            "Space play \u2022 \u25c0 \u25b6 history \u2022 A autoplay",
            "R ask again \u2022 X close \u2022 scroll",
        ):
            self.screen.blit(self.small.render(line, True, DIM), (PANEL_X, fy))
            fy += 18
        self.quit_rect = pygame.Rect(PANEL_X + 250, WIN_H - 66, 110, 56)
        pygame.draw.rect(self.screen, (120, 50, 50), self.quit_rect, border_radius=6)
        img = self.small.render("Quit (Q)", True, TEXT)
        self.screen.blit(img, img.get_rect(center=self.quit_rect.center))

    # ---- events ----
    def slider_value(self, x: int) -> float:
        frac = min(1.0, max(0.0, (x - self.slider_rect.x) / self.slider_rect.w))
        return round(frac * 2.0 * 10) / 10

    def handle_click(self, pos: tuple[int, int]):
        if self.btn_next.rect.collidepoint(pos) and not self.btn_next.disabled:
            self.advance()
            return
        if self.btn_back.rect.collidepoint(pos):
            self.game.history.back()
            return
        if self.btn_fwd.rect.collidepoint(pos):
            self.game.history.forward()
            return
        if self.detail_head_rect is not None and self.detail_head_rect.collidepoint(pos):
            self.expanded_ply = None
            self.detail_head_rect = None
            return
        for r, i in self.move_line_rects:
            if r.collidepoint(pos):
                self.expanded_ply = None if self.expanded_ply == i else i
                self.detail_scroll = 0
                return
        for m, r in self.mode_rects.items():
            if r.collidepoint(pos):
                self.autoplay = m
                self.accum_ms = 0.0
        if self.speed_rect.collidepoint(pos):
            self.speed_idx = (self.speed_idx + 1) % len(SPEEDS)
        for i, r in enumerate(self.preset_rects):
            if r.collidepoint(pos):
                self.temperature = TEMP_PRESETS[i][1]
        if self.slider_rect.collidepoint(pos):
            self.temperature = self.slider_value(pos[0])
            self.temp_drag = True
        if self.arrow_rect.collidepoint(pos):
            self.show_arrows = not self.show_arrows
        if self.topk_rect.collidepoint(pos):
            self.top_k_idx = (self.top_k_idx + 1) % len(TOP_KS)
        if getattr(self, "ask_rect", None) is not None and self.ask_rect.collidepoint(pos):
            self.refetch()
            return
        if self.quit_rect is not None and self.quit_rect.collidepoint(pos):
            self.quit_requested = True
            return

    def refetch(self):
        """Forget the cached ideas and ask Jev again (costs one API call)."""
        if self.game.board.turn != chess.WHITE or not self.game.history.at_tip:
            return
        self.preview_dist = None
        self.preview_fen = None
        self.fetch_failed_fen = None
        self.do_fetch()

    def run(self):
        try:
            self._loop()
        finally:
            self.game.close()
            pygame.quit()

    def _loop(self):
        while not self.quit_requested:
            dt = self.clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                        self.advance()
                    elif event.key == pygame.K_LEFT:
                        self.game.history.back()
                    elif event.key == pygame.K_RIGHT:
                        self.game.history.forward()
                    elif event.key == pygame.K_a:
                        i = AUTOPLAY_MODES.index(self.autoplay)
                        self.autoplay = AUTOPLAY_MODES[(i + 1) % len(AUTOPLAY_MODES)]
                    elif event.key == pygame.K_r:
                        self.refetch()
                    elif event.key == pygame.K_x:
                        self.expanded_ply = None
                    elif event.key in (pygame.K_q, pygame.K_ESCAPE):
                        return
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self.temp_drag = False
                if event.type == pygame.MOUSEMOTION and self.temp_drag:
                    self.temperature = self.slider_value(event.pos[0])
                if event.type == pygame.MOUSEWHEEL:
                    if self.expanded_ply is None:
                        self.move_scroll = max(0, self.move_scroll - event.y)
                    else:
                        self.detail_scroll = max(0, self.detail_scroll - event.y)

            # autoplay
            board_now = self.game.board
            side = "white" if board_now.turn == chess.WHITE else "black"
            if should_auto_step(self.autoplay, side, self.game.history.at_tip, board_now.is_game_over()):
                self.accum_ms += dt
                if self.accum_ms >= SPEEDS[self.speed_idx] * 1000:
                    self.advance()
            else:
                self.accum_ms = 0.0

            # auto-fetch Jev's ideas whenever it's Jev's turn at the tip with
            # no cached preview (right after Stockfish moves, and at game start)
            tip = self.game.board
            if (
                self.game.history.at_tip
                and not tip.is_game_over()
                and tip.turn == chess.WHITE
                and self.preview_fen != tip.fen()
                and self.fetch_failed_fen != tip.fen()
            ):
                self.do_fetch()

            board = self.viewed_board()
            cur = self.game.history.current()
            self.btn_next.disabled = not self.game.history.at_tip or board.is_game_over()
            self.btn_next.label = (
                "Lock in Jev's move ▶"
                if self.has_preview() and self.viewed_is_tip(board)
                else "Next move ▶"
            )
            self.screen.fill(BG)
            self.draw_board(board, cur.move_uci if cur else None)
            if self.show_arrows and self.viewed_is_tip(board) and self.has_preview():
                self.draw_arrows(self.preview_dist.probs)
            elif self.show_arrows and cur is not None and cur.side == "white" and cur.jev_probs:
                self.draw_arrows(cur.jev_probs)
            self.draw_panel(board)
            # Buttons last: draw_panel paints the panel background over this area.
            self.btn_back.draw(self.screen, self.small)
            self.btn_next.draw(self.screen, self.small)
            self.btn_fwd.draw(self.screen, self.small)
            pygame.display.flip()


def main() -> None:
    ap = argparse.ArgumentParser(description="Jev Chess pygame UI.")
    ap.add_argument("--engine-path", default=None)
    ap.add_argument("--engine-time", type=float, default=0.3)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--autoplay", default="opponent", choices=list(AUTOPLAY_MODES))
    args = ap.parse_args()
    App(args).run()


if __name__ == "__main__":
    main()
