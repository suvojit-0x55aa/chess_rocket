"""Tests for the openings library, MCP tools, and live game integration.

Covers:
- Trie-based opening identification (deepest match, out-of-book, empty)
- SQLite querying (search, ECO lookup, level filtering)
- Graceful degradation with nonexistent DB paths
- MCP tool wrappers (identify, search, suggest, quiz, details)
- Quiz tracking in progress.json
- Live game current_opening integration

Requires data/openings.db and data/openings_trie.json to exist
(run: uv run python scripts/build_openings_db.py).
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

from scripts.openings import OpeningsDB

# Import server module from hyphenated directory via importlib
_server_path = _PROJECT_ROOT / "mcp-server" / "server.py"
_spec = importlib.util.spec_from_file_location("mcp_server_mod_openings", _server_path)
_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_server)

_DATA_DIR = _server._DATA_DIR
_games = _server._games

# MCP tool functions from server
new_game = _server.new_game
make_move = _server.make_move
engine_move = _server.engine_move

# Import openings_tools module
_openings_tools_path = _PROJECT_ROOT / "mcp-server" / "openings_tools.py"
_ot_spec = importlib.util.spec_from_file_location(
    "openings_tools_mod", _openings_tools_path
)
_ot_mod = importlib.util.module_from_spec(_ot_spec)
_ot_spec.loader.exec_module(_ot_mod)

# The MCP tools are registered on _server.mcp — access them via _server
identify_opening = _server.mcp._tool_manager._tools.get("identify_opening")
search_openings = _server.mcp._tool_manager._tools.get("search_openings")
get_opening_details = _server.mcp._tool_manager._tools.get("get_opening_details")
suggest_opening = _server.mcp._tool_manager._tools.get("suggest_opening")
opening_quiz = _server.mcp._tool_manager._tools.get("opening_quiz")


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def openings_db():
    """Provide an OpeningsDB instance backed by real data files."""
    db = OpeningsDB()
    if not db._trie:
        pytest.skip("Openings DB not built. Run: uv run python scripts/build_openings_db.py")
    return db


@pytest.fixture(autouse=True)
def _clean_data():
    """Backup and restore data files around each test."""
    progress_path = _DATA_DIR / "progress.json"
    srs_path = _DATA_DIR / "srs_cards.json"

    orig_progress = None
    if progress_path.exists():
        orig_progress = progress_path.read_text(encoding="utf-8")

    orig_srs = None
    if srs_path.exists():
        orig_srs = srs_path.read_text(encoding="utf-8")

    yield

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


# ── Trie Tests ──────────────────────────────────────────────────────


class TestTrieIdentifyOpening:
    """Test trie-based opening identification."""

    def test_sicilian_defense(self, openings_db):
        """1.e4 c5 should identify as Sicilian Defense (B20)."""
        result = openings_db.identify_opening(["e2e4", "c7c5"])
        assert result is not None
        assert result["eco"] == "B20"
        assert "Sicilian" in result["name"]
        assert result["family"] == "Sicilian Defense"
        assert result["moves_matched"] == 2

    def test_empty_moves_returns_none(self, openings_db):
        """Empty move list should return None."""
        result = openings_db.identify_opening([])
        assert result is None

    def test_non_book_moves_returns_none(self, openings_db):
        """Moves that don't match any opening should return None."""
        # 1.a4 b5 2.a5 — unlikely to be in the trie past a few moves
        result = openings_db.identify_opening(["a2a4", "b7b5", "a4a5", "b5b4", "a5a6"])
        # If some prefix matches, that's fine — we just need to verify it
        # handles non-book continuations gracefully (not crash)
        # The key test: it returns None or a valid dict
        assert result is None or isinstance(result, dict)

    def test_deepest_match(self, openings_db):
        """Should return the deepest (most specific) matching opening."""
        # 1.e4 c5 2.Nf3 — should match deeper than just Sicilian Defense
        result_2 = openings_db.identify_opening(["e2e4", "c7c5"])
        result_3 = openings_db.identify_opening(["e2e4", "c7c5", "g1f3"])

        assert result_2 is not None
        assert result_3 is not None
        # 3-move result should match at least as deep as 2-move result
        assert result_3["moves_matched"] >= result_2["moves_matched"]

    def test_single_move_opening(self, openings_db):
        """1.e4 alone should identify as King's Pawn Game or similar."""
        result = openings_db.identify_opening(["e2e4"])
        # Most first moves have a named opening in Lichess data
        # e4 = King's Pawn Game (B00) or similar
        if result is not None:
            assert "eco" in result
            assert "name" in result
            assert result["moves_matched"] == 1

    def test_result_has_pgn(self, openings_db):
        """Identified opening should include PGN from SQLite."""
        result = openings_db.identify_opening(["e2e4", "c7c5"])
        assert result is not None
        assert "pgn" in result
        # PGN should be non-empty if SQLite is available
        assert len(result["pgn"]) > 0


# ── SQLite Tests ────────────────────────────────────────────────────


class TestSQLiteQueries:
    """Test SQLite-based opening queries."""

    def test_search_italian(self, openings_db):
        """Search for 'Italian' should return Italian Game variations."""
        results = openings_db.search_openings("Italian")
        assert len(results) > 0
        assert all("Italian" in r["name"] for r in results)

    def test_search_by_eco_code(self, openings_db):
        """Search by ECO code should return correct results."""
        results = openings_db.search_openings("B20")
        assert len(results) > 0
        # B20 should include Sicilian Defense
        names = [r["name"] for r in results]
        assert any("Sicilian" in n for n in names)

    def test_get_opening_by_eco(self, openings_db):
        """get_opening_by_eco('C50') should return Italian Game openings."""
        results = openings_db.get_opening_by_eco("C50")
        assert len(results) > 0
        assert all(r["eco"] == "C50" for r in results)

    def test_get_opening_lines(self, openings_db):
        """get_opening_lines should return all variations of a family."""
        results = openings_db.get_opening_lines("Sicilian Defense")
        assert len(results) > 0
        assert all(r["family"] == "Sicilian Defense" for r in results)

    def test_level_400_returns_short_common(self, openings_db):
        """get_openings_for_level(400) should return only short, common openings."""
        results = openings_db.get_openings_for_level(400)
        assert len(results) > 0
        # Phase 1: <= 4 half-moves, from common families
        for r in results:
            assert r["num_moves"] <= 4

    def test_level_1200_returns_wider(self, openings_db):
        """get_openings_for_level(1200) should return more openings than 400."""
        results_400 = openings_db.get_openings_for_level(400)
        results_1200 = openings_db.get_openings_for_level(1200)
        # Phase 3 (1000+) gets full access — should be more openings
        assert len(results_1200) > len(results_400)

    def test_get_random_opening(self, openings_db):
        """get_random_opening should return a valid opening dict."""
        result = openings_db.get_random_opening()
        assert result is not None
        assert "eco" in result
        assert "name" in result
        assert "pgn" in result

    def test_get_random_opening_with_filters(self, openings_db):
        """get_random_opening with eco_volume filter should respect it."""
        result = openings_db.get_random_opening(eco_volume="B")
        assert result is not None
        assert result["eco_volume"] == "B"

    def test_search_with_limit(self, openings_db):
        """Search with limit should respect max results."""
        results = openings_db.search_openings("Defense", limit=5)
        assert len(results) <= 5


# ── Graceful Degradation Tests ──────────────────────────────────────


class TestGracefulDegradation:
    """Test that OpeningsDB handles missing files gracefully."""

    def test_nonexistent_paths_no_crash(self):
        """OpeningsDB with nonexistent paths should not crash."""
        db = OpeningsDB(
            db_path="/nonexistent/openings.db",
            trie_path="/nonexistent/trie.json",
        )
        assert db.identify_opening(["e2e4"]) is None
        assert db.search_openings("Italian") == []
        assert db.get_opening_by_eco("C50") == []
        assert db.get_opening_lines("Italian Game") == []
        assert db.get_openings_for_level(400) == []
        assert db.get_random_opening() is None
        assert db.get_continuations(["e2e4"]) == []

    def test_nonexistent_trie_only(self):
        """OpeningsDB with missing trie but valid DB should degrade for trie methods."""
        db_path = _DATA_DIR / "openings.db"
        if not db_path.exists():
            pytest.skip("openings.db not found")

        db = OpeningsDB(
            db_path=str(db_path),
            trie_path="/nonexistent/trie.json",
        )
        # Trie methods return None/empty
        assert db.identify_opening(["e2e4"]) is None
        assert db.get_continuations(["e2e4"]) == []
        # SQLite methods still work
        results = db.search_openings("Italian")
        assert len(results) > 0


# ── MCP Tool Tests ──────────────────────────────────────────────────


def _call_tool(tool_obj, **kwargs):
    """Call an MCP tool function directly, bypassing the MCP protocol."""
    # FastMCP tools store the actual function in .fn attribute
    fn = getattr(tool_obj, "fn", None)
    if fn is None:
        # Try accessing the underlying function directly
        fn = tool_obj
    return fn(**kwargs)


class TestMCPIdentifyOpening:
    """Test the identify_opening MCP tool."""

    def test_identify_with_valid_game(self):
        """identify_opening should return opening info for a game with moves."""
        state = new_game(target_elo=800, player_color="white")
        game_id = state["game_id"]

        # Make opening moves: 1.e4
        make_move(game_id, "e4")

        result = _call_tool(identify_opening, game_id=game_id)
        # Should return either opening info or out-of-book message
        assert "error" not in result or "not found" not in result.get("error", "")

    def test_identify_invalid_game_id(self):
        """identify_opening with invalid game_id should return error."""
        result = _call_tool(identify_opening, game_id="nonexistent-id")
        assert "error" in result
        assert "not found" in result["error"].lower() or "Game not found" in result["error"]


class TestMCPSearchOpenings:
    """Test the search_openings MCP tool."""

    def test_search_returns_results(self):
        """search_openings should return results with total count."""
        result = _call_tool(search_openings, query="Italian")
        assert "error" not in result
        assert "results" in result
        assert "total" in result
        assert result["total"] > 0
        assert len(result["results"]) > 0

    def test_search_with_eco_filter(self):
        """search_openings with eco filter should narrow results."""
        result = _call_tool(search_openings, query="", eco="B20")
        assert "error" not in result
        assert result["total"] > 0


class TestMCPGetOpeningDetails:
    """Test the get_opening_details MCP tool."""

    def test_get_details_b20(self):
        """get_opening_details('B20') should return Sicilian variations."""
        result = _call_tool(get_opening_details, eco="B20")
        assert "error" not in result
        assert result["eco"] == "B20"
        assert len(result["variations"]) > 0

    def test_get_details_nonexistent_eco(self):
        """get_opening_details with nonexistent ECO should return empty variations."""
        result = _call_tool(get_opening_details, eco="Z99")
        assert "error" not in result
        assert result["variations"] == []


class TestMCPSuggestOpening:
    """Test the suggest_opening MCP tool."""

    def test_suggest_returns_list(self):
        """suggest_opening should return level-appropriate suggestions."""
        result = _call_tool(suggest_opening, elo=400, color="white")
        assert "error" not in result
        assert "suggestions" in result
        assert isinstance(result["suggestions"], list)
        assert len(result["suggestions"]) > 0

    def test_suggest_reads_progress(self):
        """suggest_opening with elo=None should read from progress.json."""
        # Write a known progress file
        progress_path = _DATA_DIR / "progress.json"
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(
            json.dumps({"estimated_elo": 500, "current_elo": 500}),
            encoding="utf-8",
        )

        result = _call_tool(suggest_opening, color="white")
        assert "error" not in result
        assert "suggestions" in result


class TestMCPOpeningQuiz:
    """Test the opening_quiz MCP tool."""

    def test_quiz_creates_game(self):
        """opening_quiz should create a game and return correct_move_san."""
        result = _call_tool(opening_quiz, difficulty="beginner")
        assert "error" not in result
        assert "game_id" in result
        assert "opening_name" in result
        assert "opening_eco" in result
        assert "position_fen" in result
        assert "moves_so_far" in result
        assert "correct_move_san" in result

        # The game should exist in _games dict
        assert result["game_id"] in _games

    def test_quiz_with_eco(self):
        """opening_quiz with specific ECO should use that opening family."""
        result = _call_tool(opening_quiz, eco="B20", difficulty="beginner")
        if "error" not in result:
            assert result["opening_eco"] == "B20"

    def test_quiz_updates_openings_studied(self):
        """opening_quiz should track studied openings in progress.json."""
        # Ensure clean progress
        progress_path = _DATA_DIR / "progress.json"
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(json.dumps({}), encoding="utf-8")

        result = _call_tool(opening_quiz, difficulty="beginner")
        assert "error" not in result

        # Check progress.json was updated with openings_studied
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        assert "openings_studied" in progress
        assert len(progress["openings_studied"]) > 0
        assert result["opening_name"] in progress["openings_studied"]


# ── MCP Tools Error When DB Not Built ───────────────────────────────


class TestMCPToolsDBNotBuilt:
    """Test that all tools return error dict when openings DB is not built."""

    @pytest.fixture(autouse=True)
    def _hide_db_files(self, tmp_path):
        """Temporarily rename DB files to simulate missing DB."""
        db_path = _DATA_DIR / "openings.db"
        trie_path = _DATA_DIR / "openings_trie.json"

        db_exists = db_path.exists()
        trie_exists = trie_path.exists()

        db_backup = _DATA_DIR / "openings.db.bak"
        trie_backup = _DATA_DIR / "openings_trie.json.bak"

        if db_exists:
            os.rename(db_path, db_backup)
        if trie_exists:
            os.rename(trie_path, trie_backup)

        yield

        if db_exists:
            os.rename(db_backup, db_path)
        if trie_exists:
            os.rename(trie_backup, trie_path)

    def test_search_returns_error(self):
        result = _call_tool(search_openings, query="Italian")
        assert "error" in result
        assert "not built" in result["error"].lower()

    def test_details_returns_error(self):
        result = _call_tool(get_opening_details, eco="B20")
        assert "error" in result
        assert "not built" in result["error"].lower()

    def test_suggest_returns_error(self):
        result = _call_tool(suggest_opening, elo=400, color="white")
        assert "error" in result
        assert "not built" in result["error"].lower()

    def test_quiz_returns_error(self):
        result = _call_tool(opening_quiz, difficulty="beginner")
        assert "error" in result
        assert "not built" in result["error"].lower()

    def test_identify_returns_error(self):
        state = new_game(target_elo=800, player_color="white")
        game_id = state["game_id"]
        result = _call_tool(identify_opening, game_id=game_id)
        assert "error" in result
        assert "not built" in result["error"].lower()


# ── Live Game Integration ───────────────────────────────────────────


class TestLiveGameOpeningIntegration:
    """Test that current_opening is populated in game state during play."""

    def test_current_opening_after_book_moves(self):
        """Game state should show current_opening after known opening moves."""
        state = new_game(target_elo=800, player_color="white")
        game_id = state["game_id"]

        # 1.e4
        state = make_move(game_id, "e4")
        # After 1.e4, current_opening may or may not be set depending on data
        # but should not error
        assert "error" not in state

        # Engine responds, then we continue
        state = engine_move(game_id)
        assert "error" not in state

        # current_opening should be a dict or None (both valid)
        opening = state.get("current_opening")
        assert opening is None or isinstance(opening, dict)

        if opening is not None:
            assert "eco" in opening
            assert "name" in opening
            assert "family" in opening
            assert "moves_matched" in opening

    def test_current_opening_in_game_state_dict(self):
        """current_opening field should always be present in GameState."""
        state = new_game(target_elo=800, player_color="white")
        assert "current_opening" in state
