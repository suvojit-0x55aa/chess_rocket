"""End-to-end integration test for the post-game flow.

Exercises the full chain: auto PGN save, save_session, batch SRS
card creation, and export. Uses real Stockfish (must be installed).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

# Add project root so imports resolve
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Import server module from hyphenated directory via importlib
_server_path = _PROJECT_ROOT / "mcp-server" / "server.py"
_spec = importlib.util.spec_from_file_location("mcp_server_mod", _server_path)
_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_server)

_DATA_DIR = _server._DATA_DIR
_games = _server._games
create_srs_cards_from_game = _server.create_srs_cards_from_game
engine_move = _server.engine_move
evaluate_move = _server.evaluate_move
make_move = _server.make_move
new_game = _server.new_game
save_session = _server.save_session
set_position = _server.set_position

from scripts.export import export_progress  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_data():
    """Backup and restore data files around each test."""
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
    pre_pgn_files = set(games_dir.glob("*.pgn")) if games_dir.exists() else set()
    pre_session_files = set(sessions_dir.glob("*.json")) if sessions_dir.exists() else set()

    # Reset progress to known default state for test isolation
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
            if f not in pre_pgn_files:
                f.unlink(missing_ok=True)

    if sessions_dir.exists():
        for f in sessions_dir.glob("*.json"):
            if f not in pre_session_files:
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

    # Close all engine processes before clearing game store
    for game in _games.values():
        engine = game.get("engine")
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass

    _games.clear()


def _play_to_checkmate() -> tuple[str, dict]:
    """Set up a position where white can mate in 1 and deliver it.

    Uses the scholar's mate final position: white Qf7 is checkmate.

    Returns:
        Tuple of (game_id, final_state).
    """
    # Position: White to move, Qxf7# is checkmate
    # After 1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6?? -> Qxf7#
    mate_fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
    result = set_position(mate_fen)
    game_id = result["game_id"]

    # Qxf7# is checkmate
    final_state = make_move(game_id, "Qxf7#")
    assert final_state.get("is_game_over") is True
    assert final_state.get("result") == "1-0"

    return game_id, final_state


class TestAutoSavePGN:
    """Test that PGN is automatically saved when a game ends."""

    def test_pgn_auto_saved_on_checkmate(self):
        games_dir = _DATA_DIR / "games"
        pre_files = set(games_dir.glob("*.pgn")) if games_dir.exists() else set()

        _play_to_checkmate()

        post_files = set(games_dir.glob("*.pgn"))
        new_files = post_files - pre_files
        assert len(new_files) >= 1, "Expected at least one new PGN file after checkmate"

        # Verify PGN content
        pgn_content = next(iter(new_files)).read_text(encoding="utf-8")
        assert "Chess Speedrun" in pgn_content
        assert "Chess Rocket" in pgn_content
        assert "1-0" in pgn_content


class TestSaveSession:
    """Test the save_session tool."""

    def test_save_session_updates_progress(self):
        game_id, _ = _play_to_checkmate()

        result = save_session(
            game_id=game_id,
            estimated_elo=500,
            accuracy_pct=75.0,
            lesson_name="Scholar's Mate",
            areas_for_improvement=["tactics"],
            summary="Test game",
        )

        assert "error" not in result
        assert result["session_id"] == "session_001"
        assert "session_file" in result

        # Verify progress.json was updated
        progress = json.loads(
            (_DATA_DIR / "progress.json").read_text(encoding="utf-8")
        )
        assert progress["sessions_completed"] > 0
        assert progress["streak"] > 0
        assert progress["estimated_elo"] == 500
        assert 75.0 in progress["accuracy_history"]

    def test_save_session_creates_session_log(self):
        game_id, _ = _play_to_checkmate()

        result = save_session(game_id=game_id)

        sessions_dir = _DATA_DIR / "sessions"
        session_file = sessions_dir / "session_001.json"
        assert session_file.exists()

        session_data = json.loads(session_file.read_text(encoding="utf-8"))
        assert session_data["game_id"] == game_id
        assert session_data["result"] == "1-0"

    def test_save_session_invalid_game(self):
        result = save_session(game_id="nonexistent")
        assert "error" in result

    def test_save_session_auto_computes_accuracy(self):
        """Verify save_session computes accuracy_pct from stored move evals when not provided."""
        # Set up a position where white has a clear move
        mate_fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
        result = set_position(mate_fen)
        game_id = result["game_id"]

        # Evaluate a move to populate move_evals
        evaluate_move(game_id, "Qxf7+")

        # Now deliver the mate
        make_move(game_id, "Qxf7#")

        # Save session WITHOUT providing accuracy_pct
        session_result = save_session(game_id=game_id)
        assert "error" not in session_result

        # Verify accuracy was auto-computed and stored
        progress = json.loads(
            (_DATA_DIR / "progress.json").read_text(encoding="utf-8")
        )
        assert len(progress["accuracy_history"]) == 1
        assert isinstance(progress["accuracy_history"][0], float)

    def test_save_session_no_evals_no_accuracy(self):
        """Verify accuracy_history is not appended when no evals exist and no accuracy_pct provided."""
        game_id, _ = _play_to_checkmate()

        # Save session without accuracy_pct and without any evaluate_move calls
        session_result = save_session(game_id=game_id)
        assert "error" not in session_result

        # Verify accuracy_history was NOT appended to
        progress = json.loads(
            (_DATA_DIR / "progress.json").read_text(encoding="utf-8")
        )
        assert len(progress["accuracy_history"]) == 0


class TestCreateSRSCardsFromGame:
    """Test the create_srs_cards_from_game tool."""

    def test_creates_cards_without_error(self):
        game_id, _ = _play_to_checkmate()

        result = create_srs_cards_from_game(game_id=game_id)

        assert "error" not in result
        assert result["game_id"] == game_id
        assert "total_player_moves" in result
        assert "mistakes_found" in result
        assert "cards_created" in result
        assert isinstance(result["mistakes"], list)
        assert isinstance(result["card_ids"], list)
        assert result["cards_created"] >= 0

    def test_error_on_in_progress_game(self):
        state = new_game(target_elo=800)
        game_id = state["game_id"]

        result = create_srs_cards_from_game(game_id=game_id)
        assert "error" in result

    def test_error_on_invalid_game(self):
        result = create_srs_cards_from_game(game_id="nonexistent")
        assert "error" in result


class TestExportAfterSession:
    """Test that export works with updated progress data."""

    def test_export_progress_after_session(self):
        game_id, _ = _play_to_checkmate()

        save_session(
            game_id=game_id,
            estimated_elo=550,
            accuracy_pct=80.0,
        )

        output = export_progress()
        assert output is not None
        assert len(output) > 0
        assert "550" in output
        assert "Progress Report" in output


class TestFullPostGameChain:
    """Integration test exercising the entire post-game flow end-to-end."""

    def test_full_chain(self):
        games_dir = _DATA_DIR / "games"
        pre_pgn = set(games_dir.glob("*.pgn")) if games_dir.exists() else set()

        # 1. Play a game to completion
        game_id, final_state = _play_to_checkmate()
        assert final_state["is_game_over"] is True

        # 2. Verify PGN was auto-saved
        post_pgn = set(games_dir.glob("*.pgn"))
        assert len(post_pgn - pre_pgn) >= 1

        # 3. Save session
        session_result = save_session(
            game_id=game_id,
            estimated_elo=500,
            accuracy_pct=90.0,
            lesson_name="Checkmate patterns",
            summary="Quick mate test",
        )
        assert "error" not in session_result
        assert session_result["progress"]["sessions_completed"] > 0
        assert session_result["progress"]["streak"] > 0

        # 4. Verify session log created
        sessions_dir = _DATA_DIR / "sessions"
        session_file = sessions_dir / "session_001.json"
        assert session_file.exists()

        # 5. Create SRS cards from game
        srs_result = create_srs_cards_from_game(game_id=game_id)
        assert "error" not in srs_result
        assert srs_result["cards_created"] >= 0

        # 6. Export progress
        export_output = export_progress()
        assert len(export_output) > 0
        assert "500" in export_output
