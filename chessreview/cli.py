"""Command line entry point: chessreview [games.pgn] [--player NAME] ..."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .analyzer import Analyzer, read_games
from .report import render_game, render_overall, to_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chessreview",
        description="Analyze chess.com PGN exports with Stockfish and get feedback on your play.",
    )
    parser.add_argument(
        "pgn", nargs="?",
        help="PGN file downloaded from chess.com (one or many games); leave out to pick from a list",
    )
    parser.add_argument(
        "-g", "--games-dir",
        help="folder of PGN files to pick from when no file is given (remembered for next time)",
    )
    parser.add_argument("-p", "--player", help="your chess.com username; focuses feedback on your moves")
    parser.add_argument("-d", "--depth", type=int, default=16, help="Stockfish search depth per position (default 16)")
    parser.add_argument("-e", "--engine", help="path to the Stockfish binary (default: auto-detect)")
    parser.add_argument("-t", "--threads", type=int, default=1, help="Stockfish threads (default 1)")
    parser.add_argument("-n", "--max-games", type=int, help="only analyze the first N games")
    parser.add_argument("-a", "--all-moves", action="store_true", help="list every move, not just the errors")
    parser.add_argument("--json", metavar="FILE", help="also write the full analysis to a JSON file")
    return parser


def config_path() -> Path:
    """Where the remembered games folder is stored."""
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    return Path(base) / "chessreview" / "config.json"


def load_games_dir() -> Path | None:
    try:
        folder = json.loads(config_path().read_text(encoding="utf-8")).get("games_dir")
    except (OSError, ValueError, AttributeError):
        return None
    return Path(folder) if folder else None


def save_games_dir(folder: Path) -> None:
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"games_dir": str(folder.resolve())}), encoding="utf-8")
    except OSError:
        pass  # remembering the folder is a convenience; never fail the run over it


def list_pgn_files(folder: Path) -> list[Path]:
    """PGN files in a folder, newest first."""
    try:
        files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".pgn"]
    except OSError:
        return []
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def count_games(path: Path) -> int:
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            return sum(1 for line in handle if line.startswith("[Event "))
    except OSError:
        return 0


def choose_pgn(games_dir: str | None) -> str | None:
    """Show a numbered menu of PGN files and return the chosen path (None if cancelled)."""
    if games_dir:
        folders = [Path(games_dir)]
    else:
        folders = [Path.cwd()]
        remembered = load_games_dir()
        if remembered:
            folders.append(remembered)

    files: list[Path] = []
    for folder in folders:
        files = list_pgn_files(folder)
        if files:
            break
    if not files:
        searched = " or ".join(str(f) for f in folders)
        print(f"No .pgn files found in {searched}.", file=sys.stderr)
        print("Pass a PGN file, or point at your games folder with --games-dir FOLDER.", file=sys.stderr)
        return None

    print(f"PGN files in {folder.resolve()}:")
    for number, path in enumerate(files, start=1):
        games = count_games(path)
        print(f"  {number:>2}. {path.name}  ({games} game{'s' if games != 1 else ''})")
    while True:
        try:
            answer = input(f"Pick a file [1-{len(files)}, Enter to quit]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not answer or answer.lower() in ("q", "quit"):
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(files):
            return str(files[int(answer) - 1])
        print(f"Please enter a number from 1 to {len(files)}.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.games_dir:
        if not Path(args.games_dir).is_dir():
            print(f"Not a folder: {args.games_dir}", file=sys.stderr)
            return 2
        save_games_dir(Path(args.games_dir))
    if args.pgn is None:
        args.pgn = choose_pgn(args.games_dir)
        if args.pgn is None:
            return 1
    elif not Path(args.pgn).is_file():
        print(f"File not found: {args.pgn}", file=sys.stderr)
        return 2
    save_games_dir(Path(args.pgn).parent)

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
