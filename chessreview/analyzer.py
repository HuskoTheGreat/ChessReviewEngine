"""Run Stockfish over a game and build a move-by-move review."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

import chess
import chess.engine
import chess.pgn

from .scoring import Classification, classify, format_score, game_accuracy, move_accuracy, win_percent

# A game is in the "opening" for this many full moves, and in the "endgame"
# once both sides have at most this much non-pawn material (queen = 9, rook = 5...).
OPENING_MOVES = 12
ENDGAME_MATERIAL = 13

PIECE_VALUES = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


@dataclass
class MoveReview:
    ply: int
    move_number: int
    color: chess.Color
    san: str
    uci: str
    best_san: str
    best_uci: str
    best_line: list[str]
    eval_before: str
    eval_after: str
    win_before: float
    win_after: float
    accuracy: float
    classification: Classification
    phase: str
    clock: float | None = None

    @property
    def win_drop(self) -> float:
        return max(0.0, self.win_before - self.win_after)

    @property
    def label(self) -> str:
        dots = "." if self.color == chess.WHITE else "..."
        return f"{self.move_number}{dots} {self.san}{self.classification.symbol}"


@dataclass
class GameReview:
    headers: dict[str, str]
    moves: list[MoveReview] = field(default_factory=list)

    def moves_for(self, color: chess.Color) -> list[MoveReview]:
        return [m for m in self.moves if m.color == color]

    def accuracy(self, color: chess.Color) -> float | None:
        return game_accuracy([m.accuracy for m in self.moves_for(color)])

    def count(self, color: chess.Color, classification: Classification) -> int:
        return sum(1 for m in self.moves_for(color) if m.classification == classification)

    def color_of(self, player: str | None) -> chess.Color | None:
        if not player:
            return None
        if self.headers.get("White", "").lower() == player.lower():
            return chess.WHITE
        if self.headers.get("Black", "").lower() == player.lower():
            return chess.BLACK
        return None


# How deep to look for a Stockfish download below each search folder, and folders never worth entering.
SEARCH_DEPTH = 4
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "site-packages", "src", "wiki"}


def _is_stockfish_binary(path: str) -> bool:
    name = os.path.basename(path).lower()
    if not name.startswith("stockfish") or not os.path.isfile(path):
        return False
    if os.name == "nt":
        return name.endswith(".exe")
    return "." not in name and os.access(path, os.X_OK)


def search_stockfish(roots: list[str], max_depth: int = SEARCH_DEPTH) -> str | None:
    """Look through folders (and their subfolders) for a Stockfish executable, nearest first."""
    seen = set()
    for root in roots:
        root = os.path.abspath(root)
        if root in seen or not os.path.isdir(root):
            continue
        seen.add(root)
        level = [root]
        for _ in range(max_depth + 1):
            next_level = []
            for folder in level:
                try:
                    entries = sorted(os.scandir(folder), key=lambda e: e.name)
                except OSError:
                    continue
                for entry in entries:
                    if _is_stockfish_binary(entry.path):
                        return entry.path
                    if entry.is_dir(follow_symlinks=False) and entry.name not in SKIP_DIRS:
                        next_level.append(entry.path)
            level = next_level
    return None


def find_stockfish(explicit: str | None = None) -> str:
    """Locate a Stockfish binary: --engine flag, STOCKFISH_PATH, PATH, then nearby folders."""
    candidates = [explicit, os.environ.get("STOCKFISH_PATH")]
    candidates += [shutil.which(name) for name in ("stockfish", "stockfish.exe")]
    candidates += ["/usr/games/stockfish", "/usr/local/bin/stockfish", "/opt/homebrew/bin/stockfish"]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    if explicit is None:
        # The current folder, this program's folder and the folder above it (where a
        # Stockfish zip is often unpacked next to the program), then Downloads.
        project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        roots = [os.getcwd(), project, os.path.dirname(project), os.path.join(os.path.expanduser("~"), "Downloads")]
        found = search_stockfish(roots)
        if found:
            return found
    raise FileNotFoundError(
        "Could not find Stockfish. Install it (https://stockfishchess.org/download/) and either "
        "unzip it next to this program, put it on your PATH, set STOCKFISH_PATH, or pass --engine /path/to/stockfish."
    )


def game_phase(board: chess.Board) -> str:
    if board.fullmove_number <= OPENING_MOVES:
        return "opening"
    for color in chess.COLORS:
        material = sum(len(board.pieces(piece, color)) * value for piece, value in PIECE_VALUES.items())
        if material > ENDGAME_MATERIAL:
            return "middlegame"
    return "endgame"


class Analyzer:
    """Wraps a Stockfish process; reuse one instance for many games."""

    def __init__(self, engine_path: str | None = None, depth: int = 16, threads: int = 1, hash_mb: int = 128):
        self.limit = chess.engine.Limit(depth=depth)
        self.engine = chess.engine.SimpleEngine.popen_uci(find_stockfish(engine_path))
        options = {"Threads": threads, "Hash": hash_mb}
        self.engine.configure({k: v for k, v in options.items() if k in self.engine.options})

    def close(self) -> None:
        self.engine.quit()

    def __enter__(self) -> "Analyzer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _evaluate(self, board: chess.Board) -> tuple[chess.engine.PovScore, list[chess.Move]]:
        if board.is_game_over():
            outcome = board.outcome()
            if outcome is not None and outcome.winner is not None:
                # Side to move has been checkmated.
                return chess.engine.PovScore(chess.engine.Mate(-0), board.turn), []
            return chess.engine.PovScore(chess.engine.Cp(0), board.turn), []
        info = self.engine.analyse(board, self.limit)
        return info["score"], info.get("pv", [])

    def analyze(self, game: chess.pgn.Game, progress=None) -> GameReview:
        review = GameReview(headers=dict(game.headers))
        board = game.board()
        nodes = list(game.mainline())

        score, pv = self._evaluate(board)
        for ply, node in enumerate(nodes):
            mover = board.turn
            move = node.move
            phase = game_phase(board)
            move_number = board.fullmove_number
            san = board.san(move)
            best = pv[0] if pv else move
            best_san = board.san(best)
            best_line = _pv_to_san(board, pv[:6])
            score_before = score.pov(mover)
            had_mate = score_before.is_mate() and score_before > chess.engine.Cp(0)

            board.push(move)
            score, pv = self._evaluate(board)
            score_after = score.pov(mover)

            w_before = win_percent(score_before)
            w_after = win_percent(score_after)
            played_best = move == best
            still_mating = score_after.is_mate() and score_after > chess.engine.Cp(0)
            allowed_mate = score_after.is_mate() and score_after < chess.engine.Cp(0) and not score_before.is_mate()
            review.moves.append(
                MoveReview(
                    ply=ply,
                    move_number=move_number,
                    color=mover,
                    san=san,
                    uci=move.uci(),
                    best_san=best_san,
                    best_uci=best.uci(),
                    best_line=best_line,
                    eval_before=format_score(score_before),
                    eval_after=format_score(score_after),
                    win_before=w_before,
                    win_after=w_after,
                    accuracy=100.0 if played_best else move_accuracy(w_before, w_after),
                    classification=classify(
                        w_before,
                        w_after,
                        played_best,
                        missed_mate=had_mate and not still_mating,
                        allowed_mate_from_cp=score_before.score() if allowed_mate else None,
                    ),
                    phase=phase,
                    clock=node.clock(),
                )
            )
            if progress:
                progress(ply + 1, len(nodes))
        return review


def _pv_to_san(board: chess.Board, pv: list[chess.Move]) -> list[str]:
    board = board.copy(stack=False)
    line = []
    for move in pv:
        if move not in board.legal_moves:
            break
        line.append(board.san(move))
        board.push(move)
    return line


def read_games(path: str):
    """Yield every game in a PGN file (chess.com exports can hold many)."""
    with open(path, encoding="utf-8-sig") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                return
            yield game
