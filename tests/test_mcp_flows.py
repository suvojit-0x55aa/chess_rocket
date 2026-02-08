"""Multi-tool functional flow tests for MCP server.

Exercises realistic multi-tool sequences verifying minification
across game lifecycle, opening study, SRS review, session persistence,
error paths, and response size regression.

Run:
    uv run pytest tests/test_mcp_flows.py -v          # mocked
    uv run pytest tests/test_mcp_flows.py -v --e2e     # real Stockfish
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import chess
import pytest

# Add project root so imports resolve
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Import server module from hyphenated directory via importlib
_server_path = _PROJECT_ROOT / "mcp-server" / "server.py"
_spec = importlib.util.spec_from_file_location("mcp_server_flows_test", _server_path)
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

# Opening tools (registered on mcp instance)
_mcp = _server.mcp

# Import suggest_opening and opening_quiz from the server's registered tools
sys.path.insert(0, str(_PROJECT_ROOT / "mcp-server"))
from response_schemas import GAME_STATE_SCHEMA, validate_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REMOVED_FIELDS = {"board_display", "session_number", "streak", "lesson_name"}


def _assert_minified(response: dict) -> None:
    """Assert response is a minified GameState."""
    for field in _REMOVED_FIELDS:
        assert field not in response, f"Removed field '{field}' in response"
    assert "legal_moves" not in response
    assert isinstance(response.get("legal_moves_count"), int)
    assert isinstance(response.get("move_list"), str)
    assert isinstance(response.get("accuracy"), (int, float))


def _read_tui_json() -> dict:
    """Read data/current_game.json."""
    return json.loads((_DATA_DIR / "current_game.json").read_text(encoding="utf-8"))


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
# TestGameLifecycle
# ---------------------------------------------------------------------------


class TestGameLifecycle:
    """Full game lifecycle: new_game -> moves -> game_over."""

    def test_full_lifecycle(self):
        # Start game
        state = new_game(target_elo=800)
        _assert_minified(state)
        game_id = state["game_id"]

        # Make a few moves
        state = make_move(game_id, "e4")
        _assert_minified(state)
        assert "1.e4" in state["move_list"]

        state = engine_move(game_id)
        _assert_minified(state)

        # TUI JSON should have full state throughout
        tui = _read_tui_json()
        assert "board_display" in tui
        assert isinstance(tui["legal_moves"], list)
        assert isinstance(tui["move_list"], list)

    def test_mate_lifecycle(self):
        """Play to checkmate and verify all responses minified."""
        fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
        state = set_position(fen)
        _assert_minified(state)
        game_id = state["game_id"]

        state = make_move(game_id, "Qxf7#")
        _assert_minified(state)
        assert state["is_game_over"] is True
        assert state["result"] == "1-0"

        # TUI should also reflect game over
        tui = _read_tui_json()
        assert tui["is_game_over"] is True


# ---------------------------------------------------------------------------
# TestOpeningStudyFlow
# ---------------------------------------------------------------------------


class TestOpeningStudyFlow:
    """suggest_opening -> opening_quiz -> make_move flow."""

    def test_suggest_has_no_epd(self):
        """suggest_opening results should not contain epd field."""
        # Access suggest_opening via the mcp tool manager
        suggest_tool = _mcp._tool_manager._tools.get("suggest_opening")
        if suggest_tool is None:
            pytest.skip("suggest_opening tool not registered")

        # Call the tool's function directly
        result = suggest_tool.fn(elo=400, color="white")
        if "error" in result:
            pytest.skip("Openings DB not built")

        for suggestion in result.get("suggestions", []):
            assert "epd" not in suggestion, "epd should be removed from suggestions"
            assert "name" in suggestion
            assert "eco" in suggestion
            assert "pgn" in suggestion

    def test_quiz_creates_game(self):
        """opening_quiz should create a game entry with expected fields."""
        quiz_tool = _mcp._tool_manager._tools.get("opening_quiz")
        if quiz_tool is None:
            pytest.skip("opening_quiz tool not registered")

        result = quiz_tool.fn(difficulty="beginner")
        if "error" in result:
            pytest.skip(f"Quiz error: {result['error']}")

        # Verify quiz returns expected fields
        assert "game_id" in result
        assert "opening_name" in result
        assert "opening_eco" in result
        assert "correct_move_san" in result
        assert "position_fen" in result
        assert "moves_so_far" in result

        # Verify game was registered in games dict
        assert result["game_id"] in _games


# ---------------------------------------------------------------------------
# TestSrsReviewFlow
# ---------------------------------------------------------------------------


class TestSrsReviewFlow:
    """Play game to completion -> create SRS cards."""

    def test_srs_cards_from_completed_game(self):
        fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
        state = set_position(fen)
        game_id = state["game_id"]
        make_move(game_id, "Qxf7#")

        result = create_srs_cards_from_game(game_id)
        assert "error" not in result
        assert isinstance(result["cards_created"], int)
        assert result["cards_created"] >= 0
        assert isinstance(result["mistakes"], list)


# ---------------------------------------------------------------------------
# TestSessionPersistence
# ---------------------------------------------------------------------------


class TestSessionPersistence:
    """save_session persistence and incrementing."""

    def test_session_updates_progress(self):
        state = new_game()
        game_id = state["game_id"]

        result = save_session(game_id, estimated_elo=500)
        assert "error" not in result
        assert result["progress"]["sessions_completed"] == 1
        assert result["progress"]["streak"] == 1

        # Verify progress.json was updated
        progress = json.loads(
            (_DATA_DIR / "progress.json").read_text(encoding="utf-8")
        )
        assert progress["sessions_completed"] == 1
        assert progress["current_elo"] == 500

    def test_multiple_sessions_increment(self):
        """Multiple save_session calls should increment counters."""
        state1 = new_game()
        save_session(state1["game_id"], estimated_elo=450)

        state2 = new_game()
        result2 = save_session(state2["game_id"], estimated_elo=500)
        assert result2["progress"]["sessions_completed"] == 2
        assert result2["progress"]["streak"] == 2

    def test_session_file_created(self):
        state = new_game()
        save_session(state["game_id"])
        session_file = _DATA_DIR / "sessions" / "session_001.json"
        assert session_file.exists()


# ---------------------------------------------------------------------------
# TestErrorPaths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    """All tools return proper error dicts for invalid inputs."""

    def test_get_board_invalid_game(self):
        result = get_board("nonexistent")
        assert "error" in result
        assert isinstance(result["error"], str)

    def test_make_move_invalid_game(self):
        result = make_move("nonexistent", "e4")
        assert "error" in result

    def test_engine_move_invalid_game(self):
        result = engine_move("nonexistent")
        assert "error" in result

    def test_evaluate_move_invalid_game(self):
        result = evaluate_move("nonexistent", "e4")
        assert "error" in result

    def test_undo_move_invalid_game(self):
        result = undo_move("nonexistent")
        assert "error" in result

    def test_set_difficulty_invalid_game(self):
        result = set_difficulty("nonexistent", 800)
        assert "error" in result

    def test_get_game_pgn_invalid_game(self):
        result = get_game_pgn("nonexistent")
        assert "error" in result

    def test_get_legal_moves_invalid_game(self):
        result = get_legal_moves("nonexistent")
        assert "error" in result

    def test_srs_add_card_invalid_game(self):
        result = srs_add_card("nonexistent", "e4")
        assert "error" in result

    def test_save_session_invalid_game(self):
        result = save_session("nonexistent")
        assert "error" in result

    def test_create_srs_cards_invalid_game(self):
        result = create_srs_cards_from_game("nonexistent")
        assert "error" in result

    def test_make_move_illegal(self):
        state = new_game()
        result = make_move(state["game_id"], "Qd8")  # Can't move queen on first move
        assert "error" in result

    def test_analyze_position_invalid_fen(self):
        result = analyze_position("not a valid fen")
        assert "error" in result

    def test_set_position_invalid_fen(self):
        result = set_position("not a valid fen")
        assert "error" in result

    def test_new_game_invalid_fen(self):
        result = new_game(starting_fen="bad fen")
        assert "error" in result


# ---------------------------------------------------------------------------
# TestResponseSizeRegression
# ---------------------------------------------------------------------------


class TestResponseSizeRegression:
    """Prevent response size regressions with hard thresholds."""

    def test_game_state_response_size(self):
        """Game state response should be compact even with moves played."""
        state = new_game(target_elo=800)
        game_id = state["game_id"]

        # Play a few moves (alternating player/engine)
        make_move(game_id, "e4")
        engine_move(game_id)
        make_move(game_id, "d4")
        engine_move(game_id)

        final_state = get_board(game_id)
        response_size = len(json.dumps(final_state))
        assert response_size < 500, (
            f"Game state response is {response_size} chars, expected < 500"
        )

    def test_analysis_response_size(self):
        """Analysis response should be < 400 chars."""
        response = analyze_position(chess.STARTING_FEN)
        response_size = len(json.dumps(response))
        assert response_size < 400, (
            f"Analysis response is {response_size} chars, expected < 400"
        )

    def test_evaluation_response_size(self):
        """Evaluation response should be < 200 chars."""
        state = new_game()
        response = evaluate_move(state["game_id"], "e4")
        response_size = len(json.dumps(response))
        assert response_size < 200, (
            f"Evaluation response is {response_size} chars, expected < 200"
        )
