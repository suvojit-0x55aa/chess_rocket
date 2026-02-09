"""Response schemas and minification for MCP tool responses.

Minifies MCP tool return values to reduce LLM context token waste.
data/current_game.json (TUI sync) is NOT affected — only MCP return values.

PGN string format for move_list uses standard chess notation
(1.e4 e5 2.Nf3 ...) which is natural for the LLM agent to read.
"""

from __future__ import annotations

import os


# ---------------------------------------------------------------------------
# Minification functions
# ---------------------------------------------------------------------------


def minify_game_state(state: dict) -> dict:
    """Minify a GameState dict for MCP response.

    Removes fields the LLM doesn't need, compacts move_list to PGN string,
    replaces legal_moves list with count, simplifies accuracy and opening.

    Args:
        state: Full GameState dict (as produced by _build_game_state).

    Returns:
        Minified dict with reduced token footprint.
    """
    result = {}

    # Keep core fields as-is
    for key in (
        "game_id", "fen", "last_move", "last_move_san", "eval_score",
        "player_color", "target_elo", "is_game_over", "result",
    ):
        if key in state:
            result[key] = state[key]

    # Compact move_list: JSON array -> PGN string
    move_list = state.get("move_list", [])
    if isinstance(move_list, list):
        result["move_list"] = _moves_to_pgn_string(move_list)
    else:
        result["move_list"] = move_list

    # Replace legal_moves list with count
    legal_moves = state.get("legal_moves", [])
    if isinstance(legal_moves, list):
        result["legal_moves_count"] = len(legal_moves)
    else:
        result["legal_moves_count"] = 0

    # Simplify accuracy: dict -> single float (player's color only)
    accuracy = state.get("accuracy", {"white": 0.0, "black": 0.0})
    player_color = state.get("player_color", "white")
    if isinstance(accuracy, dict):
        result["accuracy"] = accuracy.get(player_color, 0.0)
    else:
        result["accuracy"] = accuracy

    # Simplify current_opening: keep only name and eco
    opening = state.get("current_opening")
    if opening is not None and isinstance(opening, dict):
        result["current_opening"] = {
            "name": opening.get("name"),
            "eco": opening.get("eco"),
        }
    else:
        result["current_opening"] = None

    # Removed fields: board_display, session_number, streak, lesson_name

    return result


def minify_move_evaluation(evaluation: dict) -> dict:
    """Minify a MoveEvaluation dict for MCP response.

    Removes tactical_motif (always None) and is_best (redundant with
    cp_loss == 0). Truncates best_line to first 3 moves.

    Args:
        evaluation: Full MoveEvaluation dict (from dataclasses.asdict).

    Returns:
        Minified dict.
    """
    result = {}

    for key in (
        "move_san", "best_move_san", "cp_loss", "eval_before",
        "eval_after", "classification",
    ):
        if key in evaluation:
            result[key] = evaluation[key]

    # Truncate best_line to first 3 moves
    best_line = evaluation.get("best_line", [])
    if isinstance(best_line, list):
        result["best_line"] = best_line[:3]
    else:
        result["best_line"] = best_line

    # Removed fields: tactical_motif, is_best

    return result


def minify_analysis(analysis: dict) -> dict:
    """Minify an analysis response dict for MCP response.

    Truncates PV moves to 5 per line, removes null mate_in keys.

    Args:
        analysis: Full analysis dict with fen, depth, lines.

    Returns:
        Minified dict.
    """
    result = {
        "fen": analysis.get("fen"),
        "depth": analysis.get("depth"),
    }

    lines = analysis.get("lines", [])
    minified_lines = []
    for line in lines:
        ml = {
            "rank": line.get("rank"),
            "score_cp": line.get("score_cp"),
        }

        # Truncate moves to 5
        moves = line.get("moves", [])
        if isinstance(moves, list):
            ml["moves"] = moves[:5]
        else:
            ml["moves"] = moves

        # Only include mate_in when not None
        mate_in = line.get("mate_in")
        if mate_in is not None:
            ml["mate_in"] = mate_in

        minified_lines.append(ml)

    result["lines"] = minified_lines
    return result


def minify_save_session(response: dict) -> dict:
    """Minify a save_session response dict for MCP response.

    Simplifies the progress sub-dict to essential fields only.

    Args:
        response: Full save_session response with message, session_id,
                  session_file, progress.

    Returns:
        Minified dict with simplified progress.
    """
    result = {
        "message": response.get("message"),
        "session_id": response.get("session_id"),
        "session_file": response.get("session_file"),
    }

    progress = response.get("progress", {})
    result["progress"] = {
        "current_elo": progress.get("current_elo"),
        "sessions_completed": progress.get("sessions_completed"),
        "streak": progress.get("streak"),
        "total_games": progress.get("total_games"),
    }

    return result


# ---------------------------------------------------------------------------
# Helper: move list to PGN string
# ---------------------------------------------------------------------------


def _moves_to_pgn_string(moves: list[str]) -> str:
    """Convert a list of SAN moves to a PGN move string.

    E.g., ['e4', 'e5', 'Nf3', 'Nc6'] -> '1.e4 e5 2.Nf3 Nc6'

    Args:
        moves: List of SAN move strings.

    Returns:
        PGN-formatted move string.
    """
    if not moves:
        return ""

    parts = []
    for i, move in enumerate(moves):
        if i % 2 == 0:
            # White's move — prepend move number
            move_num = i // 2 + 1
            parts.append(f"{move_num}.{move}")
        else:
            # Black's move
            parts.append(move)

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Validation schemas (dict-based)
# ---------------------------------------------------------------------------

GAME_STATE_SCHEMA = {
    "game_id": str,
    "fen": str,
    "last_move": (str, type(None)),
    "last_move_san": (str, type(None)),
    "eval_score": (int, float, type(None)),
    "player_color": str,
    "target_elo": int,
    "is_game_over": bool,
    "result": (str, type(None)),
    "move_list": str,
    "legal_moves_count": int,
    "accuracy": (int, float),
    "current_opening": (dict, type(None)),
}

MOVE_EVALUATION_SCHEMA = {
    "move_san": str,
    "best_move_san": str,
    "cp_loss": int,
    "eval_before": (int, float),
    "eval_after": (int, float),
    "classification": str,
    "best_line": list,
}

ANALYSIS_SCHEMA = {
    "fen": str,
    "depth": int,
    "lines": list,
}

ERROR_SCHEMA = {
    "error": str,
}


def validate_response(response: dict, schema: dict) -> list[str]:
    """Validate a response dict against a schema.

    Only runs when CHESS_SPEEDRUN_VALIDATE=1 env var is set.

    Args:
        response: Response dict to validate.
        schema: Dict mapping key names to expected types (or tuple of types).

    Returns:
        List of validation error strings (empty = valid).
    """
    if os.environ.get("CHESS_SPEEDRUN_VALIDATE") != "1":
        return []

    errors = []

    if not isinstance(response, dict):
        errors.append(f"Response is not a dict: {type(response).__name__}")
        return errors

    for key, expected_types in schema.items():
        if key not in response:
            errors.append(f"Missing key: {key}")
            continue

        value = response[key]
        if isinstance(expected_types, tuple):
            if not isinstance(value, expected_types):
                type_names = ", ".join(t.__name__ for t in expected_types)
                errors.append(
                    f"Key '{key}': expected ({type_names}), "
                    f"got {type(value).__name__}"
                )
        else:
            if not isinstance(value, expected_types):
                errors.append(
                    f"Key '{key}': expected {expected_types.__name__}, "
                    f"got {type(value).__name__}"
                )

    return errors
