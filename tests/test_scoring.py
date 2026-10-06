import chess.engine

from chessreview.scoring import Classification, classify, format_score, game_accuracy, move_accuracy, win_percent


def test_win_percent_is_even_at_zero_and_symmetric():
    assert win_percent(chess.engine.Cp(0)) == 50
    assert round(win_percent(chess.engine.Cp(300)) + win_percent(chess.engine.Cp(-300)), 6) == 100


def test_win_percent_handles_mates():
    assert win_percent(chess.engine.Mate(3)) == 100
    assert win_percent(chess.engine.Mate(-2)) == 0
    assert win_percent(chess.engine.Mate(-0)) == 0
    assert win_percent(chess.engine.MateGiven) == 100


def test_win_percent_reads_pov_scores():
    score = chess.engine.PovScore(chess.engine.Cp(200), chess.WHITE)
    assert win_percent(score, chess.WHITE) > 50
    assert win_percent(score, chess.BLACK) < 50


def test_move_accuracy_bounds():
    assert round(move_accuracy(60, 60)) == 100
    assert move_accuracy(90, 0) == 0
    assert move_accuracy(40, 50) == move_accuracy(50, 50)


def test_game_accuracy_punishes_single_blunder():
    clean = game_accuracy([95] * 10)
    one_blunder = game_accuracy([95] * 9 + [5])
    assert clean is not None and one_blunder is not None
    assert one_blunder < clean - 15
    assert game_accuracy([]) is None


def test_classify_thresholds():
    assert classify(50, 50, played_best=True) == Classification.BEST
    assert classify(50, 47, played_best=False) == Classification.GOOD
    assert classify(50, 44, played_best=False) == Classification.INACCURACY
    assert classify(50, 39, played_best=False) == Classification.MISTAKE
    assert classify(50, 30, played_best=False) == Classification.BLUNDER
    assert classify(100, 98, played_best=False, missed_mate=True) == Classification.MISTAKE


def test_classify_allowing_mate_depends_on_prior_eval():
    assert classify(30, 0, played_best=False, allowed_mate_from_cp=-200) == Classification.BLUNDER
    assert classify(4, 0, played_best=False, allowed_mate_from_cp=-800) == Classification.MISTAKE
    assert classify(1, 0, played_best=False, allowed_mate_from_cp=-1500) == Classification.INACCURACY


def test_format_score():
    assert format_score(chess.engine.Cp(135)) == "+1.35"
    assert format_score(chess.engine.Cp(-40)) == "-0.40"
    assert format_score(chess.engine.Mate(3)) == "#3"
    assert format_score(chess.engine.Mate(-2)) == "#-2"
