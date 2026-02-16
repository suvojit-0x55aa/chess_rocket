"""Shared data models for Chess Speedrun Learning System.

GameState and MoveEvaluation are the shared contract between
the MCP server and the TUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GameState:
    """Represents the full state of a chess game for display and sync."""

    game_id: str
    fen: str
    board_display: str
    move_list: list[str] = field(default_factory=list)
    last_move: str | None = None
    last_move_san: str | None = None
    eval_score: float | None = None
    player_color: str = "white"
    target_elo: int = 800
    is_game_over: bool = False
    result: str | None = None
    legal_moves: list[str] = field(default_factory=list)
    accuracy: dict = field(default_factory=lambda: {"white": 0.0, "black": 0.0})
    session_number: int = 1
    streak: int = 0
    lesson_name: str = ""
    current_opening: dict | None = None
    material: dict = field(default_factory=lambda: {"white": 0, "black": 0})
    captured_pieces: dict = field(default_factory=lambda: {"white": [], "black": []})
    is_check: bool = False
    is_checkmate: bool = False
    is_stalemate: bool = False
    move_annotations: list[dict] = field(default_factory=list)


@dataclass
class MoveEvaluation:
    """Evaluation of a single move compared to the engine's best move."""

    move_san: str
    best_move_san: str
    cp_loss: int
    eval_before: float
    eval_after: float
    classification: str
    is_best: bool
    best_line: list[str] = field(default_factory=list)
    tactical_motif: str | None = None
