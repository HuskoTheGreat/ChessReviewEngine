"""Command line entry point: chessreview games.pgn [--player NAME] ..."""

from __future__ import annotations

import argparse
import json
import sys

from .analyzer import Analyzer, read_games
from .report import render_game, render_overall, to_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chessreview",
        description="Analyze chess.com PGN exports with Stockfish and get feedback on your play.",
    )
    parser.add_argument("pgn", help="PGN file downloaded from chess.com (one or many games)")
    parser.add_argument("-p", "--player", help="your chess.com username; focuses feedback on your moves")
    parser.add_argument("-d", "--depth", type=int, default=16, help="Stockfish search depth per position (default 16)")
    parser.add_argument("-e", "--engine", help="path to the Stockfish binary (default: auto-detect)")
    parser.add_argument("-t", "--threads", type=int, default=1, help="Stockfish threads (default 1)")
    parser.add_argument("-n", "--max-games", type=int, help="only analyze the first N games")
    parser.add_argument("-a", "--all-moves", action="store_true", help="list every move, not just the errors")
    parser.add_argument("--json", metavar="FILE", help="also write the full analysis to a JSON file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        analyzer = Analyzer(args.engine, depth=args.depth, threads=args.threads)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    reviews = []
    with analyzer:
        for index, game in enumerate(read_games(args.pgn), start=1):
            if args.max_games and index > args.max_games:
                break
            if game.errors:
                print(f"Skipping game {index}: {game.errors[0]}", file=sys.stderr)
                continue
            if not any(True for _ in game.mainline_moves()):
                continue

            def progress(done: int, total: int, index=index) -> None:
                if sys.stderr.isatty():
                    print(f"\rAnalyzing game {index}: move {done}/{total}", end="", file=sys.stderr, flush=True)

            review = analyzer.analyze(game, progress=progress)
            if sys.stderr.isatty():
                print("\r" + " " * 50 + "\r", end="", file=sys.stderr)
            reviews.append(review)
            if args.player and review.color_of(args.player) is None:
                print(f"Note: {args.player} did not play in game {index}; showing both sides.", file=sys.stderr)
            print("=" * 78)
            print(render_game(review, player=args.player, show_all=args.all_moves))
            print()

    if not reviews:
        print("No games found in the PGN file.", file=sys.stderr)
        return 1

    if args.player:
        overall = render_overall(reviews, args.player)
        if overall:
            print("=" * 78)
            print(overall)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump([to_dict(r) for r in reviews], handle, indent=2)
        print(f"\nWrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
