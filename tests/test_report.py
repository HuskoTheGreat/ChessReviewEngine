import chess

from chessreview.analyzer import GameReview, MoveReview, game_phase, read_games
from chessreview.report import feedback_tips, opening_name, render_game, render_overall
from chessreview.scoring import Classification

SAMPLE = "examples/sample_games.pgn"


def move(n, color, classification, phase="middlegame", best="Nf3", clock=None, before=50.0, after=50.0):
    return MoveReview(
        ply=n, move_number=n, color=color, san="e4", uci="e2e4", best_san=best, best_uci="g1f3",
        best_line=[best], eval_before="+0.00", eval_after="+0.00", win_before=before, win_after=after,
        accuracy=80.0, classification=classification, phase=phase, clock=clock,
    )


def test_read_games_parses_chess_com_export():
    games = list(read_games(SAMPLE))
    assert len(games) == 2
    assert games[0].headers["White"] == "SampleUser"
    assert games[0].next().clock() is not None


def test_opening_name_from_eco_url():
    assert opening_name({"ECOUrl": "https://www.chess.com/openings/Philidor-Defense"}) == "Philidor Defense"
    assert opening_name({"ECO": "C41"}) == "C41"


def test_game_phase():
    assert game_phase(chess.Board()) == "opening"
    endgame = chess.Board("8/5k2/8/3R4/8/8/2K5/8 w - - 0 40")
    assert game_phase(endgame) == "endgame"
    middlegame = chess.Board("r1bq1rk1/pp3ppp/2n2n2/3p4/3P4/2N2N2/PP3PPP/R2QKB1R w KQ - 0 20")
    assert game_phase(middlegame) == "middlegame"


def test_tips_spot_phase_tactics_and_clock():
    moves = [
        move(20, chess.WHITE, Classification.BLUNDER, phase="endgame", best="Rxe5+", clock=12),
        move(25, chess.WHITE, Classification.MISTAKE, phase="endgame", best="Qxd7", clock=8),
        move(30, chess.WHITE, Classification.GOOD, phase="endgame", before=80, after=40),
    ]
    tips = "\n".join(feedback_tips(moves))
    assert "endgame" in tips
    assert "forcing move" in tips
    assert "under 30s" in tips
    assert "winning position slip" in tips


def test_clean_game_tip():
    assert feedback_tips([move(1, chess.WHITE, Classification.BEST)]) == [
        "Clean game: no inaccuracies, mistakes or blunders found."
    ]


def test_render_focuses_on_player():
    review = GameReview(
        headers={"White": "Me", "Black": "Them", "Result": "1-0"},
        moves=[move(1, chess.WHITE, Classification.BLUNDER), move(1, chess.BLACK, Classification.MISTAKE)],
    )
    text = render_game(review, player="me")
    assert "Your key moments" in text
    assert "Black's" not in text
    assert render_overall([review], "Me") is None
    overall = render_overall([review, review], "Me")
    assert overall is not None and "2W / 0L / 0D" in overall
