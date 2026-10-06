"""Pure scoring helpers: win probability, move accuracy and move classification.

The formulas follow the ones Lichess publishes for its game analysis, which are
close to what chess.com shows in its Game Review.
"""

from __future__ import annotations

import math
from enum import Enum

import chess.engine

# Centipawn evaluations beyond this are treated as "completely winning".
CP_CEILING = 1000


class Classification(str, Enum):
    BEST = "best"
    GOOD = "good"
    INACCURACY = "inaccuracy"
    MISTAKE = "mistake"
    BLUNDER = "blunder"

    @property
    def symbol(self) -> str:
        return {
            Classification.BEST: "",
            Classification.GOOD: "",
            Classification.INACCURACY: "?!",
            Classification.MISTAKE: "?",
            Classification.BLUNDER: "??",
        }[self]


# Drop in win probability (percentage points) needed for each label.
INACCURACY_DROP = 5.0
MISTAKE_DROP = 10.0
BLUNDER_DROP = 15.0


def win_percent(score: chess.engine.PovScore | chess.engine.Score, pov: chess.Color | None = None) -> float:
    """Chance of winning (0-100) for the side the score is relative to."""
    if isinstance(score, chess.engine.PovScore):
        score = score.pov(pov if pov is not None else score.turn)
    if score.is_mate():
        # Comparing with Cp(0) also handles "mate already on the board".
        return 100.0 if score > chess.engine.Cp(0) else 0.0
    cp = max(-CP_CEILING, min(CP_CEILING, score.score()))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def move_accuracy(win_before: float, win_after: float) -> float:
    """Accuracy (0-100) of a single move given the mover's win% before and after."""
    drop = max(0.0, win_before - win_after)
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * drop) - 3.1669))


def game_accuracy(accuracies: list[float]) -> float | None:
    """Combine per-move accuracies: average of arithmetic and harmonic means.

    The harmonic mean punishes a few very bad moves, so one blunder in an
    otherwise clean game still shows up clearly.
    """
    if not accuracies:
        return None
    arithmetic = sum(accuracies) / len(accuracies)
    harmonic = len(accuracies) / sum(1 / max(a, 1.0) for a in accuracies)
    return (arithmetic + harmonic) / 2


def classify(
    win_before: float,
    win_after: float,
    played_best: bool,
    missed_mate: bool = False,
    allowed_mate_from_cp: int | None = None,
) -> Classification:
    """Label a move by how much it dropped the mover's winning chances.

    ``allowed_mate_from_cp`` is the mover's centipawn eval before a move that
    let the opponent force mate. Win% barely moves when an already bad position
    turns into a forced mate, so (like Lichess) such moves are graded by how bad
    the position was beforehand.
    """
    if played_best:
        return Classification.BEST
    drop = win_before - win_after
    if drop >= BLUNDER_DROP:
        return Classification.BLUNDER
    if allowed_mate_from_cp is not None:
        if allowed_mate_from_cp > -700:
            return Classification.BLUNDER
        if allowed_mate_from_cp > -1000:
            return Classification.MISTAKE
        return Classification.INACCURACY
    if drop >= MISTAKE_DROP or missed_mate:
        return Classification.MISTAKE
    if drop >= INACCURACY_DROP:
        return Classification.INACCURACY
    return Classification.GOOD


def format_score(score: chess.engine.Score) -> str:
    """Human readable evaluation, e.g. '+1.35', '-0.40', '#3', '#-2'."""
    mate = score.mate()
    if mate is not None:
        return f"#{mate}"
    return f"{score.score() / 100:+.2f}"
