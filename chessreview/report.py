"""Turn game reviews into readable feedback (text) or machine-readable JSON."""

from __future__ import annotations

from collections import Counter

import chess

from .analyzer import GameReview, MoveReview
from .scoring import Classification

ERRORS = (Classification.INACCURACY, Classification.MISTAKE, Classification.BLUNDER)
LOW_CLOCK_SECONDS = 30
COLOR_NAME = {chess.WHITE: "White", chess.BLACK: "Black"}


PLURALS = {"inaccuracy": "inaccuracies", "mistake": "mistakes", "blunder": "blunders"}


def plural(n: int, word: str) -> str:
    return f"{n} {word if n == 1 else PLURALS.get(word, word + 's')}"


def opening_name(headers: dict[str, str]) -> str:
    """chess.com puts the opening in the ECOUrl header; fall back to ECO/Opening."""
    url = headers.get("ECOUrl", "")
    if url:
        return url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
    return headers.get("Opening") or headers.get("ECO") or "Unknown opening"


def game_title(review: GameReview) -> str:
    h = review.headers
    white = f"{h.get('White', '?')} ({h.get('WhiteElo', '?')})"
    black = f"{h.get('Black', '?')} ({h.get('BlackElo', '?')})"
    parts = [f"{white} vs {black}", h.get("Result", "*")]
    if h.get("Date"):
        parts.append(h["Date"])
    if h.get("TimeControl"):
        parts.append(f"TC {h['TimeControl']}")
    return " | ".join(parts)


def feedback_tips(moves: list[MoveReview]) -> list[str]:
    """Plain-language observations about one player's moves."""
    tips = []
    errors = [m for m in moves if m.classification in ERRORS]
    if not moves:
        return tips
    if not errors:
        return ["Clean game: no inaccuracies, mistakes or blunders found."]

    by_phase = Counter(m.phase for m in errors)
    phase, count = by_phase.most_common(1)[0]
    if count >= 2 and count / len(errors) >= 0.5:
        advice = {
            "opening": "review the main lines of this opening and focus on development and king safety",
            "middlegame": "slow down in sharp positions and check every capture, check and threat before moving",
            "endgame": "practise basic endgames (king activity, passed pawns, rook endings)",
        }[phase]
        tips.append(f"Most of your errors ({count} of {len(errors)}) came in the {phase}: {advice}.")

    big = [m for m in errors if m.classification != Classification.INACCURACY]
    tactical = [m for m in big if _is_forcing(m.best_san)]
    if len(tactical) >= 2 or (big and len(tactical) == len(big)):
        tips.append(
            f"{len(tactical)} of your mistakes/blunders missed a forcing move (a check or capture) "
            "that was best. Before each move, scan all checks and captures for both sides."
        )

    low_clock = [m for m in big if m.clock is not None and m.clock < LOW_CLOCK_SECONDS]
    if low_clock:
        tips.append(
            f"{len(low_clock)} mistake(s)/blunder(s) happened with under {LOW_CLOCK_SECONDS}s on the clock. "
            "Spend less time early so you are not rushed later."
        )

    thrown = [m for m in moves if m.win_before >= 70 and m.win_after <= 50]
    if thrown:
        m = thrown[0]
        tips.append(f"You let a winning position slip with {m.label} (win chance {m.win_before:.0f}% -> {m.win_after:.0f}%).")
    return tips


def _is_forcing(san: str) -> bool:
    return "+" in san or "#" in san or "x" in san


def format_move(m: MoveReview) -> str:
    text = f"{m.label:<16} {m.classification.value:<11} eval {m.eval_before:>6} -> {m.eval_after:>6}"
    if m.classification in ERRORS:
        text += f"   best was {m.best_san}"
        if len(m.best_line) > 1:
            text += f" ({' '.join(m.best_line)})"
    return text


def side_summary(review: GameReview, color: chess.Color) -> str:
    acc = review.accuracy(color)
    counts = ", ".join(plural(review.count(color, c), c.value) for c in ERRORS)
    acc_text = f"{acc:.1f}%" if acc is not None else "n/a"
    return f"{COLOR_NAME[color]:<5} {review.headers.get(COLOR_NAME[color], '?'):<20} accuracy {acc_text:>6}  {counts}"


def render_game(review: GameReview, player: str | None = None, show_all: bool = False) -> str:
    lines = [game_title(review), f"Opening: {opening_name(review.headers)}"]
    if review.headers.get("Link"):
        lines.append(review.headers["Link"])
    lines.append("")
    lines += [side_summary(review, c) for c in chess.COLORS]

    you = review.color_of(player)
    colors = [you] if you is not None else list(chess.COLORS)
    for color in colors:
        who = "Your" if you is not None else f"{COLOR_NAME[color]}'s"
        moves = review.moves_for(color)
        shown = moves if show_all else [m for m in moves if m.classification in ERRORS]
        lines.append("")
        lines.append(f"{who} {'moves' if show_all else 'key moments'}:")
        lines += [f"  {format_move(m)}" for m in shown] or ["  none"]
        tips = feedback_tips(moves)
        if tips:
            lines.append("")
            lines.append(f"{who} feedback:")
            lines += [f"  - {t}" for t in tips]
    return "\n".join(lines)


def render_overall(reviews: list[GameReview], player: str) -> str | None:
    """Summary across all games for one player (needs --player)."""
    mine = [(r, r.color_of(player)) for r in reviews]
    mine = [(r, c) for r, c in mine if c is not None]
    if len(mine) < 2:
        return None
    moves = [m for r, c in mine for m in r.moves_for(c)]
    accs = [r.accuracy(c) for r, c in mine if r.accuracy(c) is not None]
    results = Counter(_result_for(r, c) for r, c in mine)
    counts = {c: sum(1 for m in moves if m.classification == c) for c in ERRORS}
    lines = [
        f"Overall for {player} across {len(mine)} games",
        f"  Record: {results['win']}W / {results['loss']}L / {results['draw']}D",
        f"  Average accuracy: {sum(accs) / len(accs):.1f}%",
        "  Per game: "
        + ", ".join(f"{counts[c] / len(mine):.1f} {PLURALS[c.value]}" for c in ERRORS),
    ]
    by_opening = Counter(opening_name(r.headers) for r, _ in mine)
    common = ", ".join(f"{name} ({n})" for name, n in by_opening.most_common(3))
    lines.append(f"  Most played openings: {common}")
    tips = feedback_tips(moves)
    if tips:
        lines.append("  Patterns:")
        lines += [f"    - {t}" for t in tips if not t.startswith("You let")]
    return "\n".join(lines)


def _result_for(review: GameReview, color: chess.Color) -> str:
    result = review.headers.get("Result", "*")
    if result == "1/2-1/2":
        return "draw"
    if result == ("1-0" if color == chess.WHITE else "0-1"):
        return "win"
    if result in ("1-0", "0-1"):
        return "loss"
    return "unfinished"


def to_dict(review: GameReview) -> dict:
    return {
        "headers": review.headers,
        "opening": opening_name(review.headers),
        "accuracy": {COLOR_NAME[c].lower(): review.accuracy(c) for c in chess.COLORS},
        "moves": [
            {
                "ply": m.ply,
                "move_number": m.move_number,
                "color": COLOR_NAME[m.color].lower(),
                "san": m.san,
                "uci": m.uci,
                "classification": m.classification.value,
                "accuracy": round(m.accuracy, 1),
                "eval_before": m.eval_before,
                "eval_after": m.eval_after,
                "win_before": round(m.win_before, 1),
                "win_after": round(m.win_after, 1),
                "best_move": m.best_san,
                "best_line": m.best_line,
                "phase": m.phase,
                "clock": m.clock,
            }
            for m in review.moves
        ],
    }
