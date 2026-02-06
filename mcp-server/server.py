"""MCP server for Chess Speedrun Learning System.

Exposes Stockfish chess tools to Claude Code via FastMCP.
Games are stored in memory keyed by UUID. Board state is synced
to data/current_game.json after every move for TUI consumption.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path so we can import scripts.*
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import chess
import chess.pgn
from mcp.server.fastmcp import FastMCP

from scripts.engine import ChessEngine
from scripts.models import GameState, MoveEvaluation
from scripts.srs import SRSManager

mcp = FastMCP("chess-speedrun")

# In-memory game store: game_id -> {engine, board, metadata}
_games: dict[str, dict] = {}

_DATA_DIR = _PROJECT_ROOT / "data"

# Register opening tools from separate module
_MCP_SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_MCP_SERVER_DIR))
from openings_tools import register_openings_tools  # noqa: E402

register_openings_tools(mcp, _games, _DATA_DIR, _PROJECT_ROOT)


def _build_game_state(game_id: str, game: dict) -> dict:
    """Build a GameState dict from the in-memory game record.

    Args:
        game_id: UUID of the game.
        game: Internal game record with engine, board, metadata.

    Returns:
        Dict representation of GameState.
    """
    board: chess.Board = game["board"]
    move_list = []
    temp = chess.Board(game["starting_fen"])
    for m in board.move_stack:
        move_list.append(temp.san(m))
        temp.push(m)

    last_move = None
    last_move_san = None
    if board.move_stack:
        last_uci = board.move_stack[-1]
        last_move = last_uci.uci()
        temp2 = board.copy()
        temp2.pop()
        last_move_san = temp2.san(last_uci)

    legal_moves = [board.san(m) for m in board.legal_moves]

    result = None
    if board.is_game_over():
        result = board.result()

    state = GameState(
        game_id=game_id,
        fen=board.fen(),
        board_display=str(board),
        move_list=move_list,
        last_move=last_move,
        last_move_san=last_move_san,
        eval_score=game.get("eval_score"),
        player_color=game["player_color"],
        target_elo=game["target_elo"],
        is_game_over=board.is_game_over(),
        result=result,
        legal_moves=legal_moves,
        accuracy=game.get("accuracy", {"white": 0.0, "black": 0.0}),
        session_number=game.get("session_number", 1),
        streak=game.get("streak", 0),
        lesson_name=game.get("lesson_name", ""),
    )
    return asdict(state)


def _sync_game_json(game_state: dict) -> None:
    """Write game state to data/current_game.json atomically.

    Uses temp file + os.replace() for atomic write.

    Args:
        game_state: GameState dict to persist.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = _DATA_DIR / "current_game.json"
    tmp = _DATA_DIR / "current_game.tmp"
    tmp.write_text(
        json.dumps(game_state, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp, target)


def _auto_save_pgn(game_id: str, game: dict) -> None:
    """Auto-save PGN file when a game ends.

    Builds PGN from the board's move stack and writes it atomically
    to data/games/. Includes player and engine Elo in headers.

    Args:
        game_id: UUID of the game.
        game: Internal game record.
    """
    board: chess.Board = game["board"]
    pgn_game = chess.pgn.Game()

    # Set up the game from starting FEN if not standard
    starting_fen = game["starting_fen"]
    if starting_fen != chess.STARTING_FEN:
        pgn_game.setup(chess.Board(starting_fen))

    # Read player Elo from progress.json
    player_elo = "unknown"
    progress_path = _DATA_DIR / "progress.json"
    try:
        if progress_path.exists():
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            player_elo = str(progress.get("current_elo", progress.get("estimated_elo", "unknown")))
    except (json.JSONDecodeError, OSError):
        pass

    target_elo = game["target_elo"]
    player_color = game["player_color"]

    # PGN headers
    now = datetime.now(timezone.utc)
    pgn_game.headers["Event"] = "Chess Speedrun"
    pgn_game.headers["Site"] = "Chess Rocket"
    pgn_game.headers["Date"] = now.strftime("%Y.%m.%d")
    pgn_game.headers["White"] = (
        f"Player (Elo {player_elo})" if player_color == "white"
        else f"Stockfish (Elo {target_elo})"
    )
    pgn_game.headers["Black"] = (
        f"Player (Elo {player_elo})" if player_color == "black"
        else f"Stockfish (Elo {target_elo})"
    )
    if board.is_game_over():
        pgn_game.headers["Result"] = board.result()

    # Replay moves into PGN
    node = pgn_game
    for m in board.move_stack:
        node = node.add_variation(m)

    # Write atomically to data/games/
    games_dir = _DATA_DIR / "games"
    games_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    filename = f"game_{timestamp}_{game_id[:8]}.pgn"
    target = games_dir / filename
    tmp = games_dir / f"{filename}.tmp"
    tmp.write_text(str(pgn_game) + "\n", encoding="utf-8")
    os.replace(tmp, target)


def _get_game(game_id: str) -> dict | None:
    """Look up a game by ID.

    Args:
        game_id: UUID string.

    Returns:
        Game record dict or None if not found.
    """
    return _games.get(game_id)


# ---------------------------------------------------------------------------
# US-004: Core game tools
# ---------------------------------------------------------------------------


@mcp.tool()
def new_game(
    target_elo: int = 800,
    player_color: str = "white",
    starting_fen: str | None = None,
) -> dict:
    """Start a new chess game against Stockfish.

    Args:
        target_elo: Engine strength (100-3500). Default 800.
        player_color: 'white' or 'black'. Default 'white'.
        starting_fen: Optional custom starting position FEN.

    Returns:
        GameState dict with initial board position.
    """
    game_id = str(uuid.uuid4())
    engine = ChessEngine()

    fen = starting_fen or chess.STARTING_FEN
    try:
        board = chess.Board(fen)
        if not board.is_valid():
            return {"error": f"Invalid FEN position: {fen}"}
    except ValueError as exc:
        return {"error": f"Invalid FEN: {exc}"}

    engine.set_difficulty(target_elo)

    game = {
        "engine": engine,
        "board": board,
        "player_color": player_color,
        "target_elo": target_elo,
        "starting_fen": fen,
        "eval_score": None,
        "accuracy": {"white": 0.0, "black": 0.0},
        "session_number": 1,
        "streak": 0,
        "lesson_name": "",
        "move_evals": [],
    }
    _games[game_id] = game

    state = _build_game_state(game_id, game)
    _sync_game_json(state)
    return state


@mcp.tool()
def get_board(game_id: str) -> dict:
    """Get the current board state for a game.

    Args:
        game_id: UUID of the game.

    Returns:
        GameState dict with current position, legal moves, and metadata.
    """
    game = _get_game(game_id)
    if game is None:
        return {"error": f"Game not found: {game_id}"}

    return _build_game_state(game_id, game)


@mcp.tool()
def make_move(game_id: str, move: str) -> dict:
    """Make a player move in SAN notation.

    Args:
        game_id: UUID of the game.
        move: Move in SAN notation (e.g., 'e4', 'Nf3', 'O-O').

    Returns:
        Updated GameState dict after the move.
    """
    game = _get_game(game_id)
    if game is None:
        return {"error": f"Game not found: {game_id}"}

    board: chess.Board = game["board"]

    if board.is_game_over():
        return {"error": f"Game is already over. Result: {board.result()}"}

    try:
        chess_move = board.parse_san(move)
    except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
        legal = [board.san(m) for m in board.legal_moves]
        return {"error": f"Illegal move: {move}. Legal moves: {legal}"}

    if chess_move not in board.legal_moves:
        legal = [board.san(m) for m in board.legal_moves]
        return {"error": f"Illegal move: {move}. Legal moves: {legal}"}

    board.push(chess_move)

    if board.is_game_over():
        _auto_save_pgn(game_id, game)

    state = _build_game_state(game_id, game)
    _sync_game_json(state)
    return state


@mcp.tool()
def engine_move(game_id: str) -> dict:
    """Have the engine make its move.

    Args:
        game_id: UUID of the game.

    Returns:
        Updated GameState dict after the engine's move.
    """
    game = _get_game(game_id)
    if game is None:
        return {"error": f"Game not found: {game_id}"}

    board: chess.Board = game["board"]

    if board.is_game_over():
        return {"error": f"Game is already over. Result: {board.result()}"}

    engine: ChessEngine = game["engine"]
    chess_move = engine.get_engine_move(board)
    board.push(chess_move)

    if board.is_game_over():
        _auto_save_pgn(game_id, game)

    state = _build_game_state(game_id, game)
    _sync_game_json(state)
    return state


# ---------------------------------------------------------------------------
# US-005: Analysis tools
# ---------------------------------------------------------------------------


@mcp.tool()
def analyze_position(
    fen: str,
    depth: int = 20,
    multipv: int = 3,
) -> dict:
    """Analyze any chess position at full strength.

    Does not require an active game. Creates a temporary engine for analysis.

    Args:
        fen: FEN string of the position to analyze.
        depth: Analysis depth (default 20).
        multipv: Number of principal variations (default 3).

    Returns:
        Dict with fen, depth, and lines (each with rank, score_cp, moves, mate_in).
    """
    try:
        board = chess.Board(fen)
        if not board.is_valid():
            return {"error": f"Invalid FEN position: {fen}"}
    except ValueError as exc:
        return {"error": f"Invalid FEN: {exc}"}

    engine = ChessEngine()
    try:
        raw_lines = engine.analyze_position(board, depth=depth, multipv=multipv)
        lines = []
        for i, line in enumerate(raw_lines, 1):
            lines.append({
                "rank": i,
                "score_cp": line["score_cp"],
                "moves": line["pv"],
                "mate_in": line["mate"],
            })
        return {"fen": fen, "depth": depth, "lines": lines}
    finally:
        engine.close()


@mcp.tool()
def evaluate_move(game_id: str, move: str) -> dict:
    """Evaluate a move's quality without making it.

    Args:
        game_id: UUID of the game.
        move: Move in SAN notation to evaluate.

    Returns:
        MoveEvaluation dict with cp_loss, classification, best_move, etc.
    """
    game = _get_game(game_id)
    if game is None:
        return {"error": f"Game not found: {game_id}"}

    board: chess.Board = game["board"]

    if board.is_game_over():
        return {"error": f"Game is already over. Result: {board.result()}"}

    try:
        chess_move = board.parse_san(move)
    except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
        legal = [board.san(m) for m in board.legal_moves]
        return {"error": f"Illegal move: {move}. Legal moves: {legal}"}

    engine: ChessEngine = game["engine"]
    evaluation = engine.evaluate_move(board, chess_move)
    return asdict(evaluation)


@mcp.tool()
def set_difficulty(game_id: str, target_elo: int) -> dict:
    """Change engine difficulty mid-game.

    Args:
        game_id: UUID of the game.
        target_elo: New target Elo (clamped to 100-3500).

    Returns:
        Confirmation dict with new difficulty settings.
    """
    game = _get_game(game_id)
    if game is None:
        return {"error": f"Game not found: {game_id}"}

    clamped_elo = max(100, min(3500, target_elo))
    engine: ChessEngine = game["engine"]
    engine.set_difficulty(clamped_elo)
    game["target_elo"] = clamped_elo

    return {
        "game_id": game_id,
        "target_elo": clamped_elo,
        "message": f"Difficulty set to Elo {clamped_elo}",
    }


# ---------------------------------------------------------------------------
# US-006: Utility tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_game_pgn(game_id: str) -> dict:
    """Export game as PGN string.

    Args:
        game_id: UUID of the game.

    Returns:
        Dict with pgn string.
    """
    game = _get_game(game_id)
    if game is None:
        return {"error": f"Game not found: {game_id}"}

    board: chess.Board = game["board"]
    pgn_game = chess.pgn.Game()

    # Set headers
    pgn_game.headers["Event"] = "Chess Speedrun"
    pgn_game.headers["White"] = (
        "Player" if game["player_color"] == "white" else f"Stockfish (Elo {game['target_elo']})"
    )
    pgn_game.headers["Black"] = (
        "Player" if game["player_color"] == "black" else f"Stockfish (Elo {game['target_elo']})"
    )

    if board.is_game_over():
        pgn_game.headers["Result"] = board.result()

    # Replay moves into PGN
    node = pgn_game
    temp = chess.Board(game["starting_fen"])
    for m in board.move_stack:
        node = node.add_variation(m)
        temp.push(m)

    return {"pgn": str(pgn_game)}


@mcp.tool()
def get_legal_moves(game_id: str, square: str | None = None) -> dict:
    """List legal moves, optionally filtered by source square.

    Args:
        game_id: UUID of the game.
        square: Optional square name (e.g., 'e2') to filter moves from.

    Returns:
        Dict with list of legal moves in SAN notation.
    """
    game = _get_game(game_id)
    if game is None:
        return {"error": f"Game not found: {game_id}"}

    board: chess.Board = game["board"]

    if square is not None:
        try:
            sq = chess.parse_square(square)
        except ValueError:
            return {"error": f"Invalid square: {square}"}

        moves = [
            board.san(m) for m in board.legal_moves if m.from_square == sq
        ]
    else:
        moves = [board.san(m) for m in board.legal_moves]

    return {"game_id": game_id, "square": square, "legal_moves": moves}


@mcp.tool()
def undo_move(game_id: str) -> dict:
    """Undo the last move. If last two were player+engine, undoes both.

    Args:
        game_id: UUID of the game.

    Returns:
        Updated GameState dict after undo.
    """
    game = _get_game(game_id)
    if game is None:
        return {"error": f"Game not found: {game_id}"}

    board: chess.Board = game["board"]

    if not board.move_stack:
        return {"error": "No moves to undo"}

    # Undo last move
    board.pop()

    # If there's still a move and it's now the opponent's turn
    # (meaning we undid one of a pair), undo the second too
    # so the player is back on their turn
    player_is_white = game["player_color"] == "white"
    player_turn = chess.WHITE if player_is_white else chess.BLACK
    if board.move_stack and board.turn != player_turn:
        board.pop()

    state = _build_game_state(game_id, game)
    _sync_game_json(state)
    return state


@mcp.tool()
def set_position(fen: str) -> dict:
    """Create a new game from a custom FEN position.

    Useful for puzzle training. Engine defaults to full strength.

    Args:
        fen: FEN string for the position.

    Returns:
        GameState dict for the new game.
    """
    try:
        board = chess.Board(fen)
        if not board.is_valid():
            return {"error": f"Invalid FEN position: {fen}"}
    except ValueError as exc:
        return {"error": f"Invalid FEN: {exc}"}

    game_id = str(uuid.uuid4())
    engine = ChessEngine()
    # Full strength for puzzle/analysis mode
    engine.set_difficulty(3000)

    player_color = "white" if board.turn == chess.WHITE else "black"

    game = {
        "engine": engine,
        "board": board,
        "player_color": player_color,
        "target_elo": 3000,
        "starting_fen": fen,
        "eval_score": None,
        "accuracy": {"white": 0.0, "black": 0.0},
        "session_number": 1,
        "streak": 0,
        "lesson_name": "",
        "move_evals": [],
    }
    _games[game_id] = game

    state = _build_game_state(game_id, game)
    _sync_game_json(state)
    return state


@mcp.tool()
def srs_add_card(
    game_id: str,
    move: str,
    explanation: str = "",
) -> dict:
    """Save current position as an SRS mistake card.

    Used by the tutor to record mistakes for spaced repetition review.

    Args:
        game_id: UUID of the game.
        move: The player's move that was a mistake (SAN).
        explanation: Why the best move is better.

    Returns:
        The newly created SRS card dict.
    """
    game = _get_game(game_id)
    if game is None:
        return {"error": f"Game not found: {game_id}"}

    board: chess.Board = game["board"]

    # Evaluate the move to get classification info
    try:
        chess_move = board.parse_san(move)
    except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
        return {"error": f"Invalid move: {move}"}

    engine: ChessEngine = game["engine"]
    evaluation = engine.evaluate_move(board, chess_move)

    srs = SRSManager()
    card = srs.add_card(
        fen=board.fen(),
        player_move=evaluation.move_san,
        best_move=evaluation.best_move_san,
        cp_loss=evaluation.cp_loss,
        classification=evaluation.classification,
        motif=evaluation.tactical_motif,
        explanation=explanation,
    )
    return card


# ---------------------------------------------------------------------------
# US-015: save_session tool
# ---------------------------------------------------------------------------


@mcp.tool()
def save_session(
    game_id: str,
    estimated_elo: int | None = None,
    accuracy_pct: float | None = None,
    lesson_name: str = "",
    areas_for_improvement: list[str] | None = None,
    summary: str = "",
) -> dict:
    """Persist all session data (progress update + session log) in one call.

    Args:
        game_id: UUID of the game.
        estimated_elo: Updated Elo estimate for the player (or None to keep existing).
        accuracy_pct: Player accuracy percentage for this game.
        lesson_name: Name of the lesson/topic covered.
        areas_for_improvement: List of areas the player should work on.
        summary: Free-text summary of the session.

    Returns:
        Dict with message, session_id, session_file, and updated progress.
    """
    game = _get_game(game_id)
    if game is None:
        return {"error": f"Game not found: {game_id}"}

    board: chess.Board = game["board"]

    # Load existing progress or defaults
    progress_path = _DATA_DIR / "progress.json"
    defaults = {
        "current_elo": 400,
        "estimated_elo": 400,
        "sessions_completed": 0,
        "streak": 0,
        "total_games": 0,
        "accuracy_history": [],
        "areas_for_improvement": [],
        "last_session": None,
    }
    try:
        if progress_path.exists():
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            for k, v in defaults.items():
                progress.setdefault(k, v)
        else:
            progress = dict(defaults)
    except (json.JSONDecodeError, OSError):
        progress = dict(defaults)

    # Update progress
    if estimated_elo is not None:
        progress["current_elo"] = estimated_elo
        progress["estimated_elo"] = estimated_elo
    progress["sessions_completed"] += 1
    progress["total_games"] += 1
    progress["streak"] += 1
    if accuracy_pct is not None:
        progress["accuracy_history"].append(accuracy_pct)
    now_iso = datetime.now(timezone.utc).isoformat()
    progress["last_session"] = now_iso
    if areas_for_improvement is not None:
        progress["areas_for_improvement"] = areas_for_improvement

    # Write progress atomically
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_progress = _DATA_DIR / "progress.json.tmp"
    tmp_progress.write_text(
        json.dumps(progress, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp_progress, progress_path)

    # Build session log
    session_num = progress["sessions_completed"]
    session_id = f"session_{session_num:03d}"

    result = None
    if board.is_game_over():
        result = board.result()
    total_moves = len(board.move_stack)

    session_log = {
        "session_id": session_id,
        "game_id": game_id,
        "date": now_iso,
        "result": result,
        "player_color": game["player_color"],
        "target_elo": game["target_elo"],
        "estimated_elo": progress["estimated_elo"],
        "total_moves": total_moves,
        "accuracy_pct": accuracy_pct,
        "lesson_name": lesson_name,
        "areas_for_improvement": areas_for_improvement or [],
        "summary": summary,
    }

    # Write session log
    sessions_dir = _DATA_DIR / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = f"{session_id}.json"
    tmp_session = sessions_dir / f"{session_file}.tmp"
    tmp_session.write_text(
        json.dumps(session_log, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp_session, sessions_dir / session_file)

    return {
        "message": f"Session {session_id} saved successfully",
        "session_id": session_id,
        "session_file": f"data/sessions/{session_file}",
        "progress": progress,
    }


# ---------------------------------------------------------------------------
# US-016: create_srs_cards_from_game tool
# ---------------------------------------------------------------------------


@mcp.tool()
def create_srs_cards_from_game(game_id: str, cp_threshold: int = 80) -> dict:
    """Batch-analyze a completed game and create SRS cards for significant mistakes.

    Replays the game, evaluates each player move at full strength (depth 20),
    and creates SRS cards for moves with cp_loss >= cp_threshold.

    Args:
        game_id: UUID of the completed game.
        cp_threshold: Minimum centipawn loss to create a card (default 80).

    Returns:
        Dict with game_id, total_player_moves, mistakes_found, cards_created,
        mistakes list, and card_ids.
    """
    game = _get_game(game_id)
    if game is None:
        return {"error": f"Game not found: {game_id}"}

    board: chess.Board = game["board"]

    if not board.is_game_over():
        return {"error": "Game is not over yet. Finish the game before creating SRS cards."}

    # No moves means nothing to analyze
    if not board.move_stack:
        return {
            "game_id": game_id,
            "total_player_moves": 0,
            "mistakes_found": 0,
            "cards_created": 0,
            "mistakes": [],
            "card_ids": [],
        }

    # Create fresh engine at full strength for analysis
    analysis_engine = ChessEngine()
    analysis_engine.set_difficulty(3000)

    player_color = game["player_color"]
    player_is_white = player_color == "white"

    replay_board = chess.Board(game["starting_fen"])
    srs = SRSManager()

    mistakes = []
    card_ids = []
    total_player_moves = 0
    move_number = 0

    try:
        for move in board.move_stack:
            move_number += 1
            is_white_turn = replay_board.turn == chess.WHITE

            # Only evaluate player moves
            if is_white_turn == player_is_white:
                total_player_moves += 1
                evaluation = analysis_engine.evaluate_move(replay_board, move)

                if evaluation.cp_loss >= cp_threshold:
                    fen = replay_board.fen()
                    explanation = (
                        f"Move {move_number}: played {evaluation.move_san} "
                        f"(best: {evaluation.best_move_san}, cp_loss: {evaluation.cp_loss})"
                    )

                    card = srs.add_card(
                        fen=fen,
                        player_move=evaluation.move_san,
                        best_move=evaluation.best_move_san,
                        cp_loss=evaluation.cp_loss,
                        classification=evaluation.classification,
                        motif=evaluation.tactical_motif,
                        explanation=explanation,
                    )
                    mistakes.append({
                        "fen": fen,
                        "move_number": move_number,
                        "player_move": evaluation.move_san,
                        "best_move": evaluation.best_move_san,
                        "cp_loss": evaluation.cp_loss,
                        "classification": evaluation.classification,
                    })
                    card_ids.append(card["id"])

            replay_board.push(move)
    finally:
        analysis_engine.close()

    return {
        "game_id": game_id,
        "total_player_moves": total_player_moves,
        "mistakes_found": len(mistakes),
        "cards_created": len(card_ids),
        "mistakes": mistakes,
        "card_ids": card_ids,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
