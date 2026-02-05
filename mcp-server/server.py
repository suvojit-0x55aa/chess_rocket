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
from pathlib import Path

# Add project root to path so we can import scripts.*
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import chess
from mcp.server.fastmcp import FastMCP

from scripts.engine import ChessEngine
from scripts.models import GameState

mcp = FastMCP("chess-speedrun")

# In-memory game store: game_id -> {engine, board, metadata}
_games: dict[str, dict] = {}

_DATA_DIR = _PROJECT_ROOT / "data"


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

    state = _build_game_state(game_id, game)
    _sync_game_json(state)
    return state


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
