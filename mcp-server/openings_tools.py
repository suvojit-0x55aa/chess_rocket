"""Opening-related MCP tools for the Chess Speedrun tutor.

Registers 5 tools on the provided FastMCP instance:
  - identify_opening
  - search_openings
  - get_opening_details
  - suggest_opening
  - opening_quiz

Called from server.py via register_openings_tools().
"""

from __future__ import annotations

import json
import os
import random
import uuid
from pathlib import Path

import chess
import chess.pgn


def register_openings_tools(mcp, games: dict, data_dir: Path, project_root: Path):
    """Register all opening-related MCP tools on the FastMCP instance.

    Args:
        mcp: FastMCP server instance.
        games: Shared in-memory games dict from server.py.
        data_dir: Path to data/ directory.
        project_root: Path to project root for imports.
    """
    # Lazy import to avoid circular deps at module level
    import sys
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from scripts.openings import OpeningsDB

    db_path = data_dir / "openings.db"
    trie_path = data_dir / "openings_trie.json"

    def _get_openings_db():
        """Get OpeningsDB instance, returning None if files don't exist."""
        if not db_path.exists() or not trie_path.exists():
            return None
        return OpeningsDB(str(db_path), str(trie_path))

    _DB_NOT_BUILT_ERROR = {
        "error": "Openings database not built. Run: uv run python scripts/build_openings_db.py"
    }

    # Import server helpers for set_position and _sync_game_json
    from scripts.engine import ChessEngine
    from scripts.models import GameState

    @mcp.tool()
    def identify_opening(game_id: str) -> dict:
        """Identify what opening is being played in the current game.

        Extracts UCI moves from the game's move history and looks up
        the deepest matching named opening.

        Args:
            game_id: UUID of the game.

        Returns:
            Dict with eco, name, family, moves_matched, pgn keys,
            or None if out of book. Returns error dict if game not found.
        """
        game = games.get(game_id)
        if game is None:
            return {"error": f"Game not found: {game_id}"}

        openings_db = _get_openings_db()
        if openings_db is None:
            return dict(_DB_NOT_BUILT_ERROR)

        board: chess.Board = game["board"]
        uci_moves = [m.uci() for m in board.move_stack]

        result = openings_db.identify_opening(uci_moves)
        if result is None:
            return {"opening": None, "message": "Position is out of book"}

        return {
            "eco": result["eco"],
            "name": result["name"],
            "family": result["family"],
            "moves_matched": result["moves_matched"],
            "pgn": result.get("pgn", ""),
        }

    @mcp.tool()
    def search_openings(
        query: str,
        eco: str | None = None,
        eco_volume: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Search the opening database by name or ECO code.

        Args:
            query: Search string (matched against name and ECO).
            eco: Optional exact ECO code filter (e.g., "B20").
            eco_volume: Optional ECO volume filter (A-E).
            limit: Maximum results to return (default 20).

        Returns:
            Dict with results list and total count.
        """
        openings_db = _get_openings_db()
        if openings_db is None:
            return dict(_DB_NOT_BUILT_ERROR)

        results = openings_db.search_openings(
            query, eco=eco, eco_volume=eco_volume, limit=limit
        )
        return {"results": results, "total": len(results)}

    @mcp.tool()
    def get_opening_details(eco: str) -> dict:
        """Get all openings matching an ECO code with family info.

        Args:
            eco: ECO code string (e.g., "B20").

        Returns:
            Dict with eco, family, and variations list.
        """
        openings_db = _get_openings_db()
        if openings_db is None:
            return dict(_DB_NOT_BUILT_ERROR)

        openings = openings_db.get_opening_by_eco(eco)
        if not openings:
            return {"eco": eco, "family": None, "variations": []}

        family = openings[0].get("family", "")
        return {"eco": eco, "family": family, "variations": openings}

    @mcp.tool()
    def suggest_opening(
        elo: int | None = None,
        color: str = "white",
    ) -> dict:
        """Suggest level-appropriate openings for study.

        Reads player Elo from progress.json if not provided.

        Args:
            elo: Player Elo for filtering. Reads from progress.json if None.
            color: 'white' or 'black' (for filtering relevant openings).

        Returns:
            Dict with suggestions list of opening dicts.
        """
        openings_db = _get_openings_db()
        if openings_db is None:
            return dict(_DB_NOT_BUILT_ERROR)

        # Read elo from progress.json if not provided
        if elo is None:
            progress_path = data_dir / "progress.json"
            try:
                if progress_path.exists():
                    progress = json.loads(
                        progress_path.read_text(encoding="utf-8")
                    )
                    elo = progress.get(
                        "estimated_elo", progress.get("current_elo", 400)
                    )
                else:
                    elo = 400
            except (json.JSONDecodeError, OSError):
                elo = 400

        all_openings = openings_db.get_openings_for_level(elo)
        if not all_openings:
            return {"suggestions": []}

        # Filter by color preference:
        # White openings start with e2e4, d2d4, c2c4, etc.
        # Black openings are responses (2nd move onwards)
        # Simple heuristic: for white, pick openings where white moves first;
        # for black, pick openings that are responses to common white openings
        suggestions = []
        seen_families = set()

        for opening in all_openings:
            family = opening.get("family", "")
            if family in seen_families:
                continue

            pgn = opening.get("pgn", "")
            # Basic color filter: white openings typically named after first move
            # Black openings are "Defense" or responses
            is_defense = "defense" in family.lower() or "defence" in family.lower()
            if color == "white" and is_defense:
                continue
            if color == "black" and not is_defense and "gambit" not in family.lower():
                # For black, include defenses and gambit responses
                # But also include Indian, Sicilian, etc.
                if not any(
                    kw in family.lower()
                    for kw in ["indian", "sicilian", "french", "caro", "dutch", "benoni", "pirc", "alekhine", "scandinavian", "philidor", "petrov"]
                ):
                    continue

            seen_families.add(family)
            suggestions.append({
                "name": opening["name"],
                "eco": opening["eco"],
                "pgn": pgn,
                "epd": opening.get("epd", ""),
            })

            if len(suggestions) >= 10:
                break

        return {"suggestions": suggestions}

    @mcp.tool()
    def opening_quiz(
        eco: str | None = None,
        difficulty: str = "beginner",
    ) -> dict:
        """Quiz the player on opening moves.

        Picks an opening, plays N-1 moves, sets up the position as a real
        game, and asks the player for the next correct move.

        Args:
            eco: Optional ECO code to quiz on. Random if None.
            difficulty: 'beginner', 'intermediate', or 'advanced'.

        Returns:
            Dict with game_id, opening_name, opening_eco, position_fen,
            moves_so_far, correct_move_san.
        """
        openings_db = _get_openings_db()
        if openings_db is None:
            return dict(_DB_NOT_BUILT_ERROR)

        # Determine move range by difficulty
        if difficulty == "beginner":
            max_moves = 4
        elif difficulty == "intermediate":
            max_moves = 8
        else:
            max_moves = None

        # Load progress for openings_studied tracking
        progress_path = data_dir / "progress.json"
        progress = {}
        try:
            if progress_path.exists():
                progress = json.loads(
                    progress_path.read_text(encoding="utf-8")
                )
        except (json.JSONDecodeError, OSError):
            progress = {}

        openings_studied = progress.get("openings_studied", [])

        # Pick an opening
        opening = None
        if eco:
            candidates = openings_db.get_opening_by_eco(eco)
            if candidates:
                # Filter out already studied
                unstudied = [
                    o for o in candidates
                    if o["name"] not in openings_studied
                ]
                if not unstudied:
                    # Reset studied list for this eco
                    openings_studied = [
                        s for s in openings_studied
                        if not any(c["name"] == s for c in candidates)
                    ]
                    unstudied = candidates
                opening = random.choice(unstudied)
        else:
            # Get random opening with move constraints
            for _ in range(20):  # Try up to 20 times to find unstudied
                candidate = openings_db.get_random_opening(
                    max_moves=max_moves
                )
                if candidate and candidate["name"] not in openings_studied:
                    opening = candidate
                    break
            if opening is None:
                # Reset and try once more
                openings_studied = []
                opening = openings_db.get_random_opening(
                    max_moves=max_moves
                )

        if opening is None:
            return {"error": "No suitable opening found for quiz"}

        # Parse the opening PGN to get moves
        pgn_text = opening.get("pgn", "")
        if not pgn_text:
            return {"error": "Opening has no PGN data"}

        # Parse PGN moves using python-chess
        import io
        game_pgn = chess.pgn.read_game(io.StringIO(f"[Result \"*\"]\n{pgn_text} *"))
        if game_pgn is None:
            return {"error": "Failed to parse opening PGN"}

        moves = list(game_pgn.mainline_moves())
        if len(moves) < 2:
            return {"error": "Opening too short for quiz"}

        # Play N-1 moves, quiz on the Nth
        quiz_move_idx = min(len(moves) - 1, random.randint(1, len(moves) - 1))
        board = chess.Board()
        moves_so_far = []

        for i, m in enumerate(moves):
            if i >= quiz_move_idx:
                break
            moves_so_far.append(board.san(m))
            board.push(m)

        # The correct move is the next one
        correct_move = moves[quiz_move_idx]
        correct_move_san = board.san(correct_move)
        position_fen = board.fen()

        # Create a real game via set_position pattern
        game_id = str(uuid.uuid4())
        engine = ChessEngine()
        engine.set_difficulty(3000)
        player_color = "white" if board.turn == chess.WHITE else "black"

        quiz_game = {
            "engine": engine,
            "board": board.copy(),
            "player_color": player_color,
            "target_elo": 3000,
            "starting_fen": position_fen,
            "eval_score": None,
            "accuracy": {"white": 0.0, "black": 0.0},
            "session_number": 1,
            "streak": 0,
            "lesson_name": f"Opening Quiz: {opening['name']}",
            "move_evals": [],
        }
        games[game_id] = quiz_game

        # Track studied opening
        openings_studied.append(opening["name"])
        progress["openings_studied"] = openings_studied

        # Write progress atomically
        data_dir.mkdir(parents=True, exist_ok=True)
        tmp = data_dir / "progress.json.tmp"
        tmp.write_text(
            json.dumps(progress, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, progress_path)

        return {
            "game_id": game_id,
            "opening_name": opening["name"],
            "opening_eco": opening["eco"],
            "position_fen": position_fen,
            "moves_so_far": moves_so_far,
            "correct_move_san": correct_move_san,
        }
