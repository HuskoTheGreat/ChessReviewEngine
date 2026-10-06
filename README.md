# Chess Review Engine

Analyze your downloaded chess.com games with Stockfish and get feedback on your play:
per-move evaluations, inaccuracies / mistakes / blunders with the best move you missed,
an accuracy score for each side, and plain-language tips about patterns in your errors.

## Setup

1. Install Python 3.9 or newer.
2. Install Stockfish from <https://stockfishchess.org/download/>.
   - Windows: unzip it somewhere, e.g. `C:\Tools\stockfish\stockfish.exe`.
   - macOS: `brew install stockfish`. Linux: `sudo apt install stockfish`.
3. From this folder, install the program:

   ```
   pip install -e .
   ```

The program finds Stockfish on your `PATH`, or by searching the current folder, the program's folder,
the folder above it and your Downloads folder, so unzipping Stockfish next to this program is enough.
Otherwise set `STOCKFISH_PATH` or pass `--engine`:

```
chessreview games.pgn --engine "C:\Tools\stockfish\stockfish.exe"
```

## Getting your games from chess.com

- One game: open it, click **Share** → **PGN** → **Download**.
- Many games: go to **Archive** (chess.com/games/archive), tick the games, and click **Download**.
  You get a single `.pgn` file with all of them.

## Usage

```
chessreview my_games.pgn --player YourChessComName
```

`--player` focuses the feedback on your moves and adds an overall summary across all the games in the file.

Leave out the file name and the program lists the `.pgn` files in the current folder (newest first)
and asks which one to review. If the current folder has none, it uses the folder of the last PGN
you reviewed, or one you set with `--games-dir`:

```
chessreview --games-dir "C:\Users\you\Documents\Chess Games" --player YourChessComName
```

| Option | What it does |
| --- | --- |
| `-p, --player NAME` | Your chess.com username |
| `-g, --games-dir DIR` | Folder to pick PGN files from when no file is given (remembered) |
| `-d, --depth N` | Stockfish depth per position (default 16; higher is slower and stronger) |
| `-n, --max-games N` | Only analyze the first N games |
| `-a, --all-moves` | List every move, not just the errors |
| `-t, --threads N` | Stockfish CPU threads |
| `--json FILE` | Also save the full analysis as JSON |

You can also run it without installing: `python -m chessreview my_games.pgn`.

Try it on the included sample: `chessreview examples/sample_games.pgn --player SampleUser`

## Example output

```
SampleUser (1250) vs Opponent1 (1310) | 0-1 | 2026.10.01 | TC 600
Opening: Italian Game Blackburne Shilling Gambit

White SampleUser           accuracy  64.1%  0 inaccuracies, 1 mistake, 3 blunders
Black Opponent1            accuracy  94.2%  1 inaccuracy, 0 mistakes, 0 blunders

Your key moments:
  4. Nxe5??        blunder     eval  +1.17 ->  -0.75   best was Nxd4 (Nxd4 exd4 O-O Nf6 Re1 h5)
  5. Nxf7??        blunder     eval  -0.42 ->  -4.42   best was Bxf7+ (Bxf7+ Kd8 d3 Qxe5 c3 Ne6)
  6. Rf1?          mistake     eval  -4.36 ->  -7.19   best was d3 (d3 d5 Bxd5 Qxh1+ Kd2 Qxh2)
  7. Be2??         blunder     eval  -6.51 ->    #-1   best was Qe2 (Qe2 Nxe2 d3 Qe7 Bg5 Nf6)

Your feedback:
  - Most of your errors (4 of 4) came in the opening: review the main lines of this opening and focus on development and king safety.
  - 2 of your mistakes/blunders missed a forcing move (a check or capture) that was best. Before each move, scan all checks and captures for both sides.
```

## How moves are judged

Each evaluation is converted to a winning chance (0–100%) for the player who moved. A move is
an **inaccuracy** if it drops that chance by 5+ points, a **mistake** at 10+, a **blunder** at 15+
(the same scale Lichess uses). Letting the opponent force mate is graded by how bad the position
already was, and missing a forced mate you had counts as at least a mistake. Accuracy uses the
Lichess per-move accuracy formula, combined so that a single blunder noticeably lowers the score.
Numbers will be close to chess.com's Game Review but not identical, since chess.com's formula is private.

Games are split into phases (opening = first 12 moves, endgame = little material left) so the
feedback can tell you where your errors cluster. If the PGN has clock times (chess.com exports do),
errors made with under 30 seconds left are called out.

## Development

```
pip install -e ".[dev]"
pytest
```

The engine test is skipped automatically when Stockfish isn't installed.
