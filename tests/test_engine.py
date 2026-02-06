"""Pytest tests for ChessEngine class.

Tests mock Stockfish so they don't require the actual binary.
Covers: initialization, game management, difficulty settings,
move classification, engine moves, and move evaluation.
"""

from __future__ import annotations

import chess
import chess.engine
import pytest
from unittest.mock import MagicMock, patch

from scripts.engine import ChessEngine, _classify_move, _find_stockfish
from scripts.models import MoveEvaluation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_engine() -> MagicMock:
    """Create a mock SimpleEngine that passes basic checks."""
    eng = MagicMock(spec=chess.engine.SimpleEngine)
    eng.ping = MagicMock()
    eng.quit = MagicMock()
    eng.configure = MagicMock()
    return eng


@pytest.fixture
def mock_popen():
    """Patch popen_uci and shutil.which so ChessEngine can be constructed."""
    eng = _make_mock_engine()
    with patch("chess.engine.SimpleEngine.popen_uci", return_value=eng) as popen, \
         patch("scripts.engine.shutil.which", return_value="/opt/homebrew/bin/stockfish"), \
         patch("scripts.engine.Path.is_file", return_value=True):
        yield popen, eng


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInitialization:

    def test_stockfish_not_found(self):
        with patch("scripts.engine.Path.is_file", return_value=False), \
             patch("scripts.engine.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="Stockfish not found"):
                _find_stockfish()

    def test_stockfish_found_via_which(self):
        with patch("scripts.engine.Path.is_file", return_value=False), \
             patch("scripts.engine.shutil.which", return_value="/usr/local/bin/stockfish"):
            assert _find_stockfish() == "/usr/local/bin/stockfish"

    def test_stockfish_found_via_path(self):
        with patch("scripts.engine.Path.is_file", return_value=True), \
             patch("scripts.engine.shutil.which", return_value=None):
            result = _find_stockfish()
            assert result == "/opt/homebrew/bin/stockfish"

    def test_constructor_calls_popen(self, mock_popen):
        popen, eng = mock_popen
        engine = ChessEngine()
        popen.assert_called()
        assert engine is not None


# ---------------------------------------------------------------------------
# Game management
# ---------------------------------------------------------------------------


class TestGameManagement:

    def test_new_game_default(self, mock_popen):
        _, _ = mock_popen
        engine = ChessEngine()
        board = engine.new_game()
        assert isinstance(board, chess.Board)
        assert board.fen() == chess.STARTING_FEN

    def test_new_game_custom_fen(self, mock_popen):
        _, _ = mock_popen
        custom_fen = "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2"
        engine = ChessEngine()
        board = engine.new_game(starting_fen=custom_fen)
        # Board may normalize FEN slightly; check key parts
        assert "pp1ppppp" in board.fen()
        assert board.turn == chess.WHITE

    def test_new_game_sets_difficulty(self, mock_popen):
        _, eng = mock_popen
        engine = ChessEngine()
        engine.new_game(target_elo=1500)
        # 1500 >= 1320 so UCI_Elo should be configured
        eng.configure.assert_called()


# ---------------------------------------------------------------------------
# Difficulty
# ---------------------------------------------------------------------------


class TestDifficulty:

    def test_sub_1320_elo_400(self, mock_popen):
        _, _ = mock_popen
        engine = ChessEngine()
        engine.set_difficulty(400)
        expected_pct = max(0, 0.85 - (400 / 1320) * 0.85)
        assert abs(engine._random_pct - expected_pct) < 0.001
        assert engine._depth == max(1, min(5, 400 // 250))  # 1

    def test_sub_1320_elo_800(self, mock_popen):
        _, _ = mock_popen
        engine = ChessEngine()
        engine.set_difficulty(800)
        expected_pct = max(0, 0.85 - (800 / 1320) * 0.85)
        assert abs(engine._random_pct - expected_pct) < 0.001
        assert engine._depth == max(1, min(5, 800 // 250))  # 3

    def test_sub_1320_elo_1200(self, mock_popen):
        _, _ = mock_popen
        engine = ChessEngine()
        engine.set_difficulty(1200)
        expected_pct = max(0, 0.85 - (1200 / 1320) * 0.85)
        assert abs(engine._random_pct - expected_pct) < 0.001
        assert engine._depth == max(1, min(5, 1200 // 250))  # 4

    def test_above_1320_elo_1500(self, mock_popen):
        _, _ = mock_popen
        engine = ChessEngine()
        engine.set_difficulty(1500)
        assert engine._random_pct == 0.0
        assert engine._use_uci_elo is True

    def test_above_1320_elo_2000(self, mock_popen):
        _, _ = mock_popen
        engine = ChessEngine()
        engine.set_difficulty(2000)
        assert engine._random_pct == 0.0
        assert engine._use_uci_elo is True


# ---------------------------------------------------------------------------
# Move classification (module-level function)
# ---------------------------------------------------------------------------


class TestMoveClassification:

    def test_best(self):
        label, is_best = _classify_move(0)
        assert label == "best"
        assert is_best is True

    def test_great(self):
        label, _ = _classify_move(15)
        assert label == "great"

    def test_good(self):
        label, _ = _classify_move(50)
        assert label == "good"

    def test_inaccuracy(self):
        label, _ = _classify_move(100)
        assert label == "inaccuracy"

    def test_mistake(self):
        label, _ = _classify_move(200)
        assert label == "mistake"

    def test_blunder(self):
        label, _ = _classify_move(400)
        assert label == "blunder"

    def test_boundaries(self):
        assert _classify_move(30)[0] == "great"
        assert _classify_move(31)[0] == "good"
        assert _classify_move(80)[0] == "good"
        assert _classify_move(81)[0] == "inaccuracy"
        assert _classify_move(150)[0] == "inaccuracy"
        assert _classify_move(151)[0] == "mistake"
        assert _classify_move(300)[0] == "mistake"
        assert _classify_move(301)[0] == "blunder"


# ---------------------------------------------------------------------------
# Engine move
# ---------------------------------------------------------------------------


class TestEngineMove:

    def test_game_over_raises(self, mock_popen):
        _, _ = mock_popen
        engine = ChessEngine()
        # Scholar's mate checkmate position
        board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
        assert board.is_game_over()
        with pytest.raises(ValueError, match="Game is already over"):
            engine.get_engine_move(board)

    def test_engine_move_returns_legal(self, mock_popen):
        _, eng = mock_popen
        board = chess.Board()
        # Make popen engine return a legal move
        mock_result = MagicMock()
        mock_result.move = chess.Move.from_uci("e2e4")
        eng.play.return_value = mock_result

        engine = ChessEngine()
        engine.set_difficulty(1500)  # use UCI_Elo path
        move = engine.get_engine_move(board)
        assert move == chess.Move.from_uci("e2e4")


# ---------------------------------------------------------------------------
# Evaluate move
# ---------------------------------------------------------------------------


class TestEvaluateMove:

    def test_returns_move_evaluation(self, mock_popen):
        _, eng = mock_popen

        # Mock analyse() to return proper structure
        # info["score"] is a PovScore; .relative returns a Score (Cp)
        def mock_analyse(board, limit, multipv=1):
            pov_score = chess.engine.PovScore(chess.engine.Cp(30), board.turn)
            return [{"score": pov_score, "pv": [chess.Move.from_uci("e2e4")]}]

        eng.analyse = mock_analyse

        engine = ChessEngine()
        board = chess.Board()
        move = chess.Move.from_uci("e2e4")
        result = engine.evaluate_move(board, move)

        assert isinstance(result, MoveEvaluation)
        assert result.move_san == "e4"
        assert result.tactical_motif is None
        assert isinstance(result.cp_loss, (int, float))
        assert result.classification in ("best", "great", "good", "inaccuracy", "mistake", "blunder")
