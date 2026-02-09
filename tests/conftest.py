"""Shared test fixtures with dual-mode support (mocked vs real Stockfish).

Usage:
    uv run pytest tests/                  # Fast, mocked engine (no Stockfish)
    uv run pytest tests/ --e2e            # Real Stockfish for integration tests

Fixtures:
    mock_chess_engine  - Patches ChessEngine with a mock returning valid moves.
                         Skipped when --e2e is passed.
    clean_data_dir     - Backs up and restores data files around each test.
    enable_validation  - Sets CHESS_SPEEDRUN_VALIDATE=1 for schema validation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import chess
import pytest

from scripts.models import MoveEvaluation

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"


# ---------------------------------------------------------------------------
# CLI option and marker registration
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    """Register --e2e CLI flag for real Stockfish tests."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run with real Stockfish engine (no mocks).",
    )


def pytest_configure(config):
    """Register the e2e marker."""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end (requires real Stockfish)"
    )


# ---------------------------------------------------------------------------
# Mock chess engine fixture
# ---------------------------------------------------------------------------


def _make_mock_engine():
    """Create a mock ChessEngine that returns valid moves."""
    mock = MagicMock()

    def _get_engine_move(board: chess.Board):
        """Return the first legal move from the board."""
        legal = list(board.legal_moves)
        if not legal:
            raise ValueError("No legal moves available")
        return legal[0]

    def _evaluate_move(board: chess.Board, move: chess.Move):
        """Return a realistic MoveEvaluation for any move."""
        move_san = board.san(move)
        # Compute best move as first legal move
        legal = list(board.legal_moves)
        best_move = legal[0] if legal else move
        best_san = board.san(best_move)
        is_best = move == best_move
        return MoveEvaluation(
            move_san=move_san,
            best_move_san=best_san,
            cp_loss=0 if is_best else 45,
            eval_before=0.3,
            eval_after=0.3 if is_best else -0.15,
            classification="best" if is_best else "good",
            is_best=is_best,
            best_line=[best_san],
            tactical_motif=None,
        )

    def _analyze_position(board: chess.Board, depth: int = 20, multipv: int = 3):
        """Return realistic analysis lines."""
        legal = list(board.legal_moves)
        lines = []
        for i in range(min(multipv, len(legal))):
            m = legal[i]
            lines.append({
                "score_cp": 30 - i * 15,
                "pv": [board.san(m)],
                "mate": None,
            })
        return lines if lines else [{"score_cp": 0, "pv": [], "mate": None}]

    mock.get_engine_move = _get_engine_move
    mock.evaluate_move = _evaluate_move
    mock.analyze_position = _analyze_position
    mock.set_difficulty = MagicMock()
    mock.close = MagicMock()

    return mock


@pytest.fixture()
def mock_chess_engine(request):
    """Patch ChessEngine with a mock that returns valid chess moves.

    Skipped when --e2e flag is passed (uses real Stockfish instead).
    The mock is applied to both scripts.engine.ChessEngine and
    the server module's imported reference.
    """
    if request.config.getoption("--e2e"):
        yield None
        return

    with patch("scripts.engine.ChessEngine", side_effect=lambda: _make_mock_engine()):
        yield


# ---------------------------------------------------------------------------
# Clean data directory fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def clean_data_dir():
    """Back up and restore data files around each test.

    Backs up progress.json and srs_cards.json, cleans up test-created
    files in data/games/ and data/sessions/ after the test.
    """
    progress_path = _DATA_DIR / "progress.json"
    srs_path = _DATA_DIR / "srs_cards.json"
    games_dir = _DATA_DIR / "games"
    sessions_dir = _DATA_DIR / "sessions"

    # Save originals
    orig_progress = None
    if progress_path.exists():
        orig_progress = progress_path.read_text(encoding="utf-8")

    orig_srs = None
    if srs_path.exists():
        orig_srs = srs_path.read_text(encoding="utf-8")

    # Track files created during test
    pre_pgn = set(games_dir.glob("*.pgn")) if games_dir.exists() else set()
    pre_session = set(sessions_dir.glob("*.json")) if sessions_dir.exists() else set()

    # Write a clean default progress for test isolation
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps({
            "current_elo": 400,
            "estimated_elo": 400,
            "sessions_completed": 0,
            "streak": 0,
            "total_games": 0,
            "accuracy_history": [],
            "areas_for_improvement": [],
            "last_session": None,
        }),
        encoding="utf-8",
    )

    yield

    # Clean up test-created files
    if games_dir.exists():
        for f in games_dir.glob("*.pgn"):
            if f not in pre_pgn:
                f.unlink(missing_ok=True)

    if sessions_dir.exists():
        for f in sessions_dir.glob("*.json"):
            if f not in pre_session:
                f.unlink(missing_ok=True)

    # Restore originals
    if orig_progress is not None:
        progress_path.write_text(orig_progress, encoding="utf-8")
    elif progress_path.exists():
        progress_path.unlink()

    if orig_srs is not None:
        srs_path.write_text(orig_srs, encoding="utf-8")
    elif srs_path.exists():
        srs_path.unlink()


# ---------------------------------------------------------------------------
# Schema validation fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def enable_validation():
    """Set CHESS_SPEEDRUN_VALIDATE=1 for the test session.

    Restores the original env var value after the test.
    """
    original = os.environ.get("CHESS_SPEEDRUN_VALIDATE")
    os.environ["CHESS_SPEEDRUN_VALIDATE"] = "1"
    yield
    if original is None:
        os.environ.pop("CHESS_SPEEDRUN_VALIDATE", None)
    else:
        os.environ["CHESS_SPEEDRUN_VALIDATE"] = original
