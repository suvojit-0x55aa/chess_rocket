"""Per-tool MCP integration tests verifying minified response shapes.

Tests all 14 MCP server tools for correct minification, TUI JSON
integrity, and schema validation. Uses mock_chess_engine fixture
from conftest.py (runs without Stockfish by default).

Run:
    uv run pytest tests/test_mcp_tools.py -v          # mocked
    uv run pytest tests/test_mcp_tools.py -v --e2e     # real Stockfish
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import chess
import pytest

# Add project root so imports resolve
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Import server module from hyphenated directory via importlib
_server_path = _PROJECT_ROOT / "mcp-server" / "server.py"
_spec = importlib.util.spec_from_file_location("mcp_server_tools_test", _server_path)
_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_server)

_DATA_DIR = _server._DATA_DIR
_games = _server._games

# Server tool functions
new_game = _server.new_game
get_board = _server.get_board
make_move = _server.make_move
engine_move = _server.engine_move
analyze_position = _server.analyze_position
evaluate_move = _server.evaluate_move
set_difficulty = _server.set_difficulty
get_game_pgn = _server.get_game_pgn
get_legal_moves = _server.get_legal_moves
undo_move = _server.undo_move
set_position = _server.set_position
srs_add_card = _server.srs_add_card
save_session = _server.save_session
create_srs_cards_from_game = _server.create_srs_cards_from_game

# Import response schemas for validation
sys.path.insert(0, str(_PROJECT_ROOT / "mcp-server"))
from response_schemas import (
    ANALYSIS_SCHEMA,
    ERROR_SCHEMA,
    GAME_STATE_SCHEMA,
    MOVE_EVALUATION_SCHEMA,
    validate_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Fields that must NOT be in minified GameState
_REMOVED_FIELDS = {"board_display", "session_number", "streak", "lesson_name"}

# Fields expected in minified GameState
_EXPECTED_FIELDS = {
    "game_id", "fen", "last_move", "last_move_san", "eval_score",
    "player_color", "target_elo", "is_game_over", "result",
    "move_list", "legal_moves_count", "accuracy", "current_opening",
}


def _assert_minified_game_state(response: dict) -> None:
    """Assert a response is a properly minified GameState."""
    for field in _REMOVED_FIELDS:
        assert field not in response, f"Removed field '{field}' found in response"
    assert "legal_moves" not in response, "legal_moves list should be replaced by legal_moves_count"
    assert isinstance(response.get("legal_moves_count"), int), "legal_moves_count must be int"
    assert isinstance(response.get("move_list"), str), "move_list must be PGN string"
    assert isinstance(response.get("accuracy"), (int, float)), "accuracy must be a number"

    errors = validate_response(response, GAME_STATE_SCHEMA)
    assert not errors, f"Schema validation errors: {errors}"


def _read_current_game_json() -> dict:
    """Read and return data/current_game.json."""
    path = _DATA_DIR / "current_game.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _clean_games():
    """Clean up game state and data files around each test."""
    progress_path = _DATA_DIR / "progress.json"
    srs_path = _DATA_DIR / "srs_cards.json"
    games_dir = _DATA_DIR / "games"
    sessions_dir = _DATA_DIR / "sessions"

    orig_progress = None
    if progress_path.exists():
        orig_progress = progress_path.read_text(encoding="utf-8")

    orig_srs = None
    if srs_path.exists():
        orig_srs = srs_path.read_text(encoding="utf-8")

    pre_pgn = set(games_dir.glob("*.pgn")) if games_dir.exists() else set()
    pre_session = set(sessions_dir.glob("*.json")) if sessions_dir.exists() else set()

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps({
            "current_elo": 400, "estimated_elo": 400,
            "sessions_completed": 0, "streak": 0, "total_games": 0,
            "accuracy_history": [], "areas_for_improvement": [],
            "last_session": None,
        }),
        encoding="utf-8",
    )

    yield

    if games_dir.exists():
        for f in games_dir.glob("*.pgn"):
            if f not in pre_pgn:
                f.unlink(missing_ok=True)

    if sessions_dir.exists():
        for f in sessions_dir.glob("*.json"):
            if f not in pre_session:
                f.unlink(missing_ok=True)

    if orig_progress is not None:
        progress_path.write_text(orig_progress, encoding="utf-8")
    elif progress_path.exists():
        progress_path.unlink()

    if orig_srs is not None:
        srs_path.write_text(orig_srs, encoding="utf-8")
    elif srs_path.exists():
        srs_path.unlink()

    for game in _games.values():
        eng = game.get("engine")
        if eng is not None:
            try:
                eng.close()
            except Exception:
                pass
    _games.clear()


# ---------------------------------------------------------------------------
# TestNewGame
# ---------------------------------------------------------------------------


class TestNewGame:
    """Verify new_game returns minified response."""

    def test_minified_response_shape(self):
        response = new_game(target_elo=800)
        _assert_minified_game_state(response)

    def test_no_board_display(self):
        response = new_game()
        assert "board_display" not in response

    def test_legal_moves_count_is_int(self):
        response = new_game()
        assert isinstance(response["legal_moves_count"], int)
        assert response["legal_moves_count"] == 20  # Starting position

    def test_move_list_is_pgn_string(self):
        response = new_game()
        assert isinstance(response["move_list"], str)
        assert response["move_list"] == ""  # No moves yet

    def test_tui_json_has_full_state(self):
        new_game(target_elo=800)
        tui = _read_current_game_json()
        # TUI must have full unminified state
        assert "board_display" in tui
        assert isinstance(tui["legal_moves"], list)
        assert isinstance(tui["move_list"], list)
        assert "session_number" in tui
        assert "streak" in tui
        assert "lesson_name" in tui

    def test_response_size(self):
        response = new_game()
        assert len(json.dumps(response)) < 800


# ---------------------------------------------------------------------------
# TestGetBoard
# ---------------------------------------------------------------------------


class TestGetBoard:
    """Verify get_board returns minified response."""

    def test_minified_response(self):
        state = new_game()
        response = get_board(state["game_id"])
        _assert_minified_game_state(response)

    def test_does_not_write_tui_json(self):
        state = new_game()
        tui_path = _DATA_DIR / "current_game.json"
        # Record mtime after new_game
        mtime_before = tui_path.stat().st_mtime_ns
        get_board(state["game_id"])
        mtime_after = tui_path.stat().st_mtime_ns
        assert mtime_before == mtime_after, "get_board should NOT write to current_game.json"

    def test_error_on_invalid_game(self):
        response = get_board("nonexistent")
        assert "error" in response
        errors = validate_response(response, ERROR_SCHEMA)
        assert not errors


# ---------------------------------------------------------------------------
# TestMakeMove
# ---------------------------------------------------------------------------


class TestMakeMove:
    """Verify make_move returns minified response."""

    def test_minified_response(self):
        state = new_game()
        response = make_move(state["game_id"], "e4")
        _assert_minified_game_state(response)

    def test_move_list_grows(self):
        state = new_game()
        response = make_move(state["game_id"], "e4")
        assert "e4" in response["move_list"]

    def test_syncs_full_state_to_json(self):
        state = new_game()
        make_move(state["game_id"], "e4")
        tui = _read_current_game_json()
        assert isinstance(tui["legal_moves"], list)
        assert isinstance(tui["move_list"], list)
        assert "e4" in tui["move_list"]

    def test_error_on_illegal_move(self):
        state = new_game()
        response = make_move(state["game_id"], "Qd8")
        assert "error" in response


# ---------------------------------------------------------------------------
# TestEngineMove
# ---------------------------------------------------------------------------


class TestEngineMove:
    """Verify engine_move returns minified response."""

    def test_minified_response(self):
        state = new_game()
        make_move(state["game_id"], "e4")
        response = engine_move(state["game_id"])
        _assert_minified_game_state(response)

    def test_syncs_full_state_to_json(self):
        state = new_game()
        make_move(state["game_id"], "e4")
        engine_move(state["game_id"])
        tui = _read_current_game_json()
        assert isinstance(tui["legal_moves"], list)
        assert len(tui["move_list"]) == 2  # e4 + engine response


# ---------------------------------------------------------------------------
# TestAnalyzePosition
# ---------------------------------------------------------------------------


class TestAnalyzePosition:
    """Verify analyze_position returns minified response."""

    def test_pv_truncated_to_5(self):
        response = analyze_position(chess.STARTING_FEN)
        assert "error" not in response
        for line in response["lines"]:
            assert len(line["moves"]) <= 5

    def test_null_mate_in_removed(self):
        response = analyze_position(chess.STARTING_FEN)
        for line in response["lines"]:
            if "mate_in" in line:
                assert line["mate_in"] is not None

    def test_invalid_fen_returns_error(self):
        response = analyze_position("invalid fen string")
        assert "error" in response

    def test_schema_validation(self):
        response = analyze_position(chess.STARTING_FEN)
        errors = validate_response(response, ANALYSIS_SCHEMA)
        assert not errors


# ---------------------------------------------------------------------------
# TestEvaluateMove
# ---------------------------------------------------------------------------


class TestEvaluateMove:
    """Verify evaluate_move returns minified response."""

    def test_tactical_motif_stripped(self):
        state = new_game()
        response = evaluate_move(state["game_id"], "e4")
        assert "error" not in response
        assert "tactical_motif" not in response

    def test_is_best_stripped(self):
        state = new_game()
        response = evaluate_move(state["game_id"], "e4")
        assert "is_best" not in response

    def test_best_line_truncated_to_3(self):
        state = new_game()
        response = evaluate_move(state["game_id"], "e4")
        assert len(response.get("best_line", [])) <= 3

    def test_schema_validation(self):
        state = new_game()
        response = evaluate_move(state["game_id"], "e4")
        errors = validate_response(response, MOVE_EVALUATION_SCHEMA)
        assert not errors


# ---------------------------------------------------------------------------
# TestSetDifficulty
# ---------------------------------------------------------------------------


class TestSetDifficulty:
    """Verify set_difficulty returns confirmation dict."""

    def test_confirmation_shape(self):
        state = new_game()
        response = set_difficulty(state["game_id"], 1200)
        assert response["game_id"] == state["game_id"]
        assert response["target_elo"] == 1200
        assert "message" in response

    def test_elo_clamping_low(self):
        state = new_game()
        response = set_difficulty(state["game_id"], 50)
        assert response["target_elo"] == 100

    def test_elo_clamping_high(self):
        state = new_game()
        response = set_difficulty(state["game_id"], 3100)
        assert response["target_elo"] == 3100

    def test_error_invalid_game(self):
        response = set_difficulty("nonexistent", 800)
        assert "error" in response


# ---------------------------------------------------------------------------
# TestGetGamePgn
# ---------------------------------------------------------------------------


class TestGetGamePgn:
    """Verify get_game_pgn returns PGN string."""

    def test_pgn_shape(self):
        state = new_game()
        make_move(state["game_id"], "e4")
        response = get_game_pgn(state["game_id"])
        assert "pgn" in response
        assert isinstance(response["pgn"], str)
        assert "e4" in response["pgn"]

    def test_error_invalid_game(self):
        response = get_game_pgn("nonexistent")
        assert "error" in response


# ---------------------------------------------------------------------------
# TestGetLegalMoves
# ---------------------------------------------------------------------------


class TestGetLegalMoves:
    """Verify get_legal_moves returns full move list (NOT minified)."""

    def test_returns_full_list(self):
        state = new_game()
        response = get_legal_moves(state["game_id"])
        assert isinstance(response["legal_moves"], list)
        assert len(response["legal_moves"]) == 20

    def test_filtered_by_square(self):
        state = new_game()
        response = get_legal_moves(state["game_id"], square="e2")
        assert isinstance(response["legal_moves"], list)
        assert len(response["legal_moves"]) == 2  # e3, e4

    def test_error_invalid_game(self):
        response = get_legal_moves("nonexistent")
        assert "error" in response


# ---------------------------------------------------------------------------
# TestUndoMove
# ---------------------------------------------------------------------------


class TestUndoMove:
    """Verify undo_move returns minified state."""

    def test_minified_response(self):
        state = new_game()
        make_move(state["game_id"], "e4")
        response = undo_move(state["game_id"])
        _assert_minified_game_state(response)

    def test_undo_pair(self):
        """Undoing after engine move should undo both player+engine moves."""
        state = new_game()
        make_move(state["game_id"], "e4")
        engine_move(state["game_id"])
        response = undo_move(state["game_id"])
        # Should be back to starting position (0 moves)
        assert response["move_list"] == ""

    def test_error_no_moves(self):
        state = new_game()
        response = undo_move(state["game_id"])
        assert "error" in response


# ---------------------------------------------------------------------------
# TestSetPosition
# ---------------------------------------------------------------------------


class TestSetPosition:
    """Verify set_position returns minified state."""

    def test_minified_response(self):
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
        response = set_position(fen)
        _assert_minified_game_state(response)

    def test_invalid_fen_returns_error(self):
        response = set_position("not a fen")
        assert "error" in response


# ---------------------------------------------------------------------------
# TestSrsAddCard
# ---------------------------------------------------------------------------


class TestSrsAddCard:
    """Verify srs_add_card returns card dict."""

    def test_card_shape(self):
        state = new_game()
        response = srs_add_card(state["game_id"], "e4", "Test explanation")
        assert "error" not in response
        assert "id" in response
        assert "fen" in response

    def test_error_invalid_game(self):
        response = srs_add_card("nonexistent", "e4")
        assert "error" in response


# ---------------------------------------------------------------------------
# TestSaveSession
# ---------------------------------------------------------------------------


class TestSaveSession:
    """Verify save_session returns minified progress."""

    def test_minified_progress(self):
        state = new_game()
        response = save_session(state["game_id"], estimated_elo=500)
        assert "error" not in response
        progress = response["progress"]
        # Only minified keys
        assert set(progress.keys()) == {
            "current_elo", "sessions_completed", "streak", "total_games",
        }
        assert progress["current_elo"] == 500
        assert progress["sessions_completed"] == 1

    def test_session_file_created(self):
        state = new_game()
        response = save_session(state["game_id"])
        sessions_dir = _DATA_DIR / "sessions"
        session_file = sessions_dir / "session_001.json"
        assert session_file.exists()

    def test_error_invalid_game(self):
        response = save_session("nonexistent")
        assert "error" in response


# ---------------------------------------------------------------------------
# TestCreateSrsCards
# ---------------------------------------------------------------------------


class TestCreateSrsCards:
    """Verify create_srs_cards_from_game returns batch result."""

    def test_result_shape(self):
        # Set up a checkmate position
        fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
        state = set_position(fen)
        game_id = state["game_id"]
        make_move(game_id, "Qxf7#")

        result = create_srs_cards_from_game(game_id)
        assert "error" not in result
        assert result["game_id"] == game_id
        assert "total_player_moves" in result
        assert "mistakes_found" in result
        assert "cards_created" in result
        assert isinstance(result["mistakes"], list)
        assert isinstance(result["card_ids"], list)

    def test_error_game_not_over(self):
        state = new_game()
        result = create_srs_cards_from_game(state["game_id"])
        assert "error" in result

    def test_error_invalid_game(self):
        result = create_srs_cards_from_game("nonexistent")
        assert "error" in result


# ---------------------------------------------------------------------------
# TestResponseSchemas
# ---------------------------------------------------------------------------


class TestResponseSchemas:
    """Validate every tool response against its schema."""

    def test_new_game_schema(self):
        response = new_game()
        errors = validate_response(response, GAME_STATE_SCHEMA)
        assert not errors, f"Schema errors: {errors}"

    def test_get_board_error_schema(self):
        response = get_board("nonexistent")
        errors = validate_response(response, ERROR_SCHEMA)
        assert not errors

    def test_make_move_error_schema(self):
        state = new_game()
        response = make_move(state["game_id"], "Qd8")  # illegal
        errors = validate_response(response, ERROR_SCHEMA)
        assert not errors

    def test_analyze_position_schema(self):
        response = analyze_position(chess.STARTING_FEN)
        errors = validate_response(response, ANALYSIS_SCHEMA)
        assert not errors

    def test_evaluate_move_schema(self):
        state = new_game()
        response = evaluate_move(state["game_id"], "e4")
        errors = validate_response(response, MOVE_EVALUATION_SCHEMA)
        assert not errors

    def test_set_position_error_schema(self):
        response = set_position("bad fen")
        errors = validate_response(response, ERROR_SCHEMA)
        assert not errors

    def test_save_session_error_schema(self):
        response = save_session("nonexistent")
        errors = validate_response(response, ERROR_SCHEMA)
        assert not errors
