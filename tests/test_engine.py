import pytest

from chessreview.analyzer import Analyzer, find_stockfish, read_games
from chessreview.scoring import Classification

try:
    find_stockfish()
    HAVE_STOCKFISH = True
except FileNotFoundError:
    HAVE_STOCKFISH = False


@pytest.mark.skipif(not HAVE_STOCKFISH, reason="Stockfish not installed")
def test_finds_blunders_in_blackburne_shilling_trap():
    game = next(read_games("examples/sample_games.pgn"))
    with Analyzer(depth=12) as analyzer:
        review = analyzer.analyze(game)
    assert len(review.moves) == 14
    white = {m.san: m.classification for m in review.moves_for(True)}
    assert white["Nxf7"] == Classification.BLUNDER
    assert white["Be2"] in (Classification.MISTAKE, Classification.BLUNDER)  # walks into Nf3#
    assert review.accuracy(False) > review.accuracy(True)
