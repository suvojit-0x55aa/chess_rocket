"""Terminal chess board UI for Chess Speedrun.

Renders a Rich-based chess board that auto-updates by watching
data/current_game.json via watchdog at ~4Hz. Supports --sample
flag for standalone testing without MCP server.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import chess
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
_CURRENT_GAME = _DATA_DIR / "current_game.json"
_SAMPLE_GAME = _DATA_DIR / "sample_game.json"

# Unicode piece symbols
_PIECE_SYMBOLS = {
    "K": "\u2654", "Q": "\u2655", "R": "\u2656", "B": "\u2657",
    "N": "\u2658", "P": "\u2659",
    "k": "\u265a", "q": "\u265b", "r": "\u265c", "b": "\u265d",
    "n": "\u265e", "p": "\u265f",
}

_LIGHT_SQ = "grey85"
_DARK_SQ = "grey50"
_HIGHLIGHT = "yellow"


def _load_game_state(path: Path) -> dict | None:
    """Load a GameState dict from a JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed dict or None if file missing/corrupt.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, dict):
            return data
        return None
    except (json.JSONDecodeError, OSError):
        return None


def render_board(state: dict) -> Layout:
    """Render the full board layout from a GameState dict.

    Args:
        state: GameState dict with fen, move_list, eval_score, etc.

    Returns:
        Rich Layout with board and sidebar.
    """
    layout = Layout()
    layout.split_row(
        Layout(name="board", ratio=2),
        Layout(name="sidebar", ratio=1),
    )

    board_panel = _render_board_panel(state)
    sidebar_panel = _render_sidebar(state)

    layout["board"].update(board_panel)
    layout["sidebar"].update(sidebar_panel)

    return layout


def _render_board_panel(state: dict) -> Panel:
    """Render the chess board as a Rich Panel.

    Args:
        state: GameState dict.

    Returns:
        Panel containing the board.
    """
    fen = state.get("fen", chess.STARTING_FEN)
    player_color = state.get("player_color", "white")
    last_move = state.get("last_move")
    is_flipped = player_color == "black"

    board = chess.Board(fen)

    # Parse last move for highlighting
    highlight_squares: set[int] = set()
    if last_move and len(last_move) >= 4:
        try:
            mv = chess.Move.from_uci(last_move)
            highlight_squares.add(mv.from_square)
            highlight_squares.add(mv.to_square)
        except (ValueError, chess.InvalidMoveError):
            pass

    # Build board table
    table = Table(show_header=False, show_edge=False, pad_edge=False,
                  box=None, padding=(0, 1))

    # Add columns: rank label + 8 squares
    table.add_column(width=2, justify="right")
    for _ in range(8):
        table.add_column(width=3, justify="center")

    ranks = range(8) if is_flipped else range(7, -1, -1)
    files = range(7, -1, -1) if is_flipped else range(8)

    for rank in ranks:
        row: list[Text] = [Text(str(rank + 1), style="bold")]
        for file in files:
            sq = chess.square(file, rank)
            piece = board.piece_at(sq)

            # Square color
            is_light = (rank + file) % 2 == 1
            bg = _LIGHT_SQ if is_light else _DARK_SQ
            if sq in highlight_squares:
                bg = _HIGHLIGHT

            if piece is not None:
                symbol = _PIECE_SYMBOLS.get(piece.symbol(), "?")
                cell = Text(f" {symbol} ", style=f"on {bg}")
            else:
                cell = Text("   ", style=f"on {bg}")

            row.append(cell)

        table.add_row(*row)

    # File labels
    file_labels = [Text("  ")]
    file_order = list(range(7, -1, -1)) if is_flipped else list(range(8))
    for f in file_order:
        file_labels.append(Text(f" {chr(ord('a') + f)} ", style="bold"))
    table.add_row(*file_labels)

    title = "Chess Speedrun"
    if state.get("is_game_over"):
        result = state.get("result", "?")
        title = f"Game Over: {result}"

    return Panel(table, title=title, border_style="blue")


def _render_sidebar(state: dict) -> Panel:
    """Render the sidebar with game info.

    Args:
        state: GameState dict.

    Returns:
        Panel containing sidebar info.
    """
    parts: list[str] = []

    # Header
    session = state.get("session_number", 1)
    streak = state.get("streak", 0)
    lesson = state.get("lesson_name", "")
    parts.append(f"[bold]Session #{session}[/bold]")
    parts.append(f"Streak: {streak}")
    if lesson:
        parts.append(f"[italic]{lesson}[/italic]")
    parts.append("")

    # Move list
    move_list = state.get("move_list", [])
    if move_list:
        parts.append("[bold]Moves:[/bold]")
        for i in range(0, len(move_list), 2):
            move_num = i // 2 + 1
            white_move = move_list[i]
            black_move = move_list[i + 1] if i + 1 < len(move_list) else ""
            parts.append(f"  {move_num}. {white_move} {black_move}")
        parts.append("")

    # Eval
    eval_score = state.get("eval_score")
    if eval_score is not None:
        bar_len = 20
        # Map eval to 0-1 range (roughly -5 to +5)
        normalized = max(0.0, min(1.0, (eval_score + 5.0) / 10.0))
        filled = int(normalized * bar_len)
        bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
        parts.append(f"[bold]Eval:[/bold] {eval_score:+.1f}")
        parts.append(f"  [{bar}]")
        parts.append("")

    # Accuracy
    accuracy = state.get("accuracy", {})
    white_acc = accuracy.get("white", 0.0)
    black_acc = accuracy.get("black", 0.0)
    parts.append("[bold]Accuracy:[/bold]")
    parts.append(f"  White: {white_acc:.1f}%")
    parts.append(f"  Black: {black_acc:.1f}%")

    # Player info
    parts.append("")
    player_color = state.get("player_color", "white")
    target_elo = state.get("target_elo", 800)
    parts.append(f"Playing as: {player_color}")
    parts.append(f"Engine Elo: {target_elo}")

    content = "\n".join(parts)
    return Panel(content, title="Info", border_style="green")


def _render_waiting() -> Panel:
    """Render a waiting message when no game is active.

    Returns:
        Panel with waiting message.
    """
    return Panel(
        Text("Waiting for game...\n\nStart a game via MCP server to see the board.",
             justify="center"),
        title="Chess Speedrun",
        border_style="dim",
    )


def _watch_loop(console: Console) -> None:
    """Watch current_game.json and auto-update display at ~4Hz.

    Args:
        console: Rich Console instance.
    """
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    last_state: dict | None = None
    state_changed = True

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event):
            nonlocal state_changed
            if event.src_path.endswith("current_game.json"):
                state_changed = True

    observer = Observer()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    observer.schedule(_Handler(), str(_DATA_DIR), recursive=False)
    observer.start()

    try:
        with Live(console=console, refresh_per_second=4) as live:
            while True:
                if state_changed:
                    state = _load_game_state(_CURRENT_GAME)
                    if state is not None:
                        last_state = state
                        live.update(render_board(state))
                    elif last_state is None:
                        live.update(_render_waiting())
                    state_changed = False
                time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


def main() -> None:
    """CLI entry point for tui.py."""
    parser = argparse.ArgumentParser(
        description="Chess Speedrun Terminal UI"
    )
    parser.add_argument(
        "--sample", action="store_true",
        help="Render sample game and exit (no watch loop)"
    )
    args = parser.parse_args()

    console = Console()

    if args.sample:
        state = _load_game_state(_SAMPLE_GAME)
        if state is None:
            console.print("[red]Sample game file not found at data/sample_game.json[/red]")
            sys.exit(1)
        console.print(render_board(state))
        return

    _watch_loop(console)


if __name__ == "__main__":
    main()
