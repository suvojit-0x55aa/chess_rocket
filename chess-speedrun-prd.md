# Chess Speedrun Learning System — Technical PRD v2

**Architecture: Claude Code as the chess tutor, with Stockfish in a separate terminal**

---

## Executive Summary

Instead of building a standalone Python app that calls the Claude API, we make **Claude Code itself the chess tutor**. The chess engine (Stockfish) and the terminal UI run as a separate process that Claude Code launches, communicates with, and orchestrates. Claude Code brings native intelligence — no API costs, no latency, no token management. The teaching, analysis, game planning, and adaptive curriculum all happen through Claude Code's natural reasoning.

The repo is structured as a **Claude Code skill + supporting scripts + MCP server** that transforms Claude Code into a grandmaster-level chess coach for absolute beginners.

---

## 1. Why Claude Code instead of Claude API

| Aspect | Claude API Approach (v1) | Claude Code Approach (v2) |
|--------|--------------------------|---------------------------|
| Teaching intelligence | API calls, prompt engineering, structured output | Native Claude reasoning — no prompts needed |
| Cost | ~$0.02-0.04/session (Sonnet) | $0/session (included in Claude Code subscription) |
| Latency | 1-3s per teaching explanation | Instant — Claude is already reasoning |
| Context | Limited to API context window per call | Full conversation history + skill context |
| Development speed | Build API client, handle errors, parse output | Claude Code reads the skill and just works |
| Iteration | Change prompts, redeploy, test | Edit SKILL.md, Claude adapts immediately |
| Multi-perspective planning | Complex prompt chaining | Claude reasons through all perspectives naturally |

The key insight: **Claude Code IS the tutor.** Stockfish is just the analysis engine. The terminal chess UI is just the interface. Claude Code does the thinking, teaching, adapting, and planning.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    CLAUDE CODE                           │
│         (Orchestrator, Tutor, Planner)                   │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Skill: chess-speedrun                           │    │
│  │  - SKILL.md (curriculum, teaching methods)       │    │
│  │  - references/ (chess pedagogy, patterns)        │    │
│  │  - scripts/ (engine wrapper, UI launcher)        │    │
│  └─────────────────────────────────────────────────┘    │
│                       │                                  │
│                       │ launches & communicates           │
│                       ▼                                  │
│  ┌─────────────────────────────────────────────────┐    │
│  │  MCP Server: chess-engine-mcp                    │    │
│  │  (Stockfish wrapper as MCP tools)                │    │
│  │  Tools:                                          │    │
│  │   - new_game(elo, color, fen?)                   │    │
│  │   - get_board()                                  │    │
│  │   - make_move(move)                              │    │
│  │   - analyze_position(depth)                      │    │
│  │   - get_best_move()                              │    │
│  │   - evaluate_move(move)                          │    │
│  │   - get_game_pgn()                               │    │
│  │   - engine_move()                                │    │
│  │   - set_difficulty(elo)                          │    │
│  └─────────────────────────────────────────────────┘    │
│                       │                                  │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Separate Terminal: Chess TUI                    │    │
│  │  (Rich/Textual live board display)               │    │
│  │  - Auto-updates on each move                     │    │
│  │  - Shows eval bar, move list, clock              │    │
│  │  - Player inputs moves here OR in Claude         │    │
│  │    Code chat                                     │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Local Storage: data/                            │    │
│  │  - progress.json (elo, phase, streak)            │    │
│  │  - sessions/ (session logs as JSON)              │    │
│  │  - games/ (PGN files)                            │    │
│  │  - srs_cards.json (spaced repetition deck)       │    │
│  │  - lesson_plans/ (generated plans)               │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### How the user interacts

The user opens Claude Code in the chess-speedrun repo and simply says:

```
> Let's start today's chess lesson
```

Claude Code reads the skill, checks `data/progress.json` for where the user left off, loads the latest lesson plan, launches the chess TUI in a side terminal, and begins the session — all through natural conversation.

Moves can be made either:
1. **In the Claude Code chat**: "I'll play e4" → Claude Code calls the MCP tool → board updates in the TUI
2. **In the TUI terminal**: Player types moves directly → game state syncs via shared file/socket

Option 1 is more natural for the teaching flow since Claude can immediately respond to each move.

---

## 3. Repo structure

```
chess-speedrun/
├── .claude/
│   └── settings.json           # Claude Code project settings
│
├── SKILL.md                    # Main skill file (Claude Code reads this)
│
├── references/
│   ├── curriculum.md           # Full curriculum: phases, lessons, prerequisites
│   ├── chess-pedagogy.md       # Teaching methodology from GM coaching research
│   ├── tactical-patterns.md    # Motif catalog: forks, pins, skewers etc.
│   ├── common-mistakes.md      # Beginner mistake patterns + how to address
│   ├── learning-science.md     # Deliberate practice, ZPD, SRS theory
│   ├── elo-milestones.md       # What skills correspond to each Elo range
│   └── opening-guide.md        # Beginner-friendly openings with explanations
│
├── scripts/
│   ├── install.sh              # Install Stockfish + Python deps
│   ├── engine.py               # Stockfish UCI wrapper (python-chess based)
│   ├── tui.py                  # Terminal chess board UI (Rich/Textual)
│   ├── analyze.py              # Position analysis CLI tool
│   ├── srs.py                  # Spaced repetition card manager
│   └── export.py               # Export session logs, PGN, progress reports
│
├── mcp-server/
│   ├── server.py               # MCP server exposing Stockfish as tools
│   ├── requirements.txt        # python-chess, stockfish, mcp
│   └── README.md               # MCP server setup instructions
│
├── data/                       # Created on first run
│   ├── progress.json           # User progress state
│   ├── srs_cards.json          # Spaced repetition deck
│   ├── sessions/               # Session logs (JSON)
│   ├── games/                  # Saved PGN files
│   └── lesson_plans/           # Generated lesson plans
│
├── puzzles/
│   ├── forks.json              # Curated puzzle positions by motif
│   ├── pins.json
│   ├── skewers.json
│   ├── back-rank.json
│   ├── checkmate-patterns.json
│   └── beginner-endgames.json
│
├── CLAUDE.md                   # Claude Code project instructions
├── pyproject.toml
└── README.md
```

---

## 4. SKILL.md — The core skill file

This is what Claude Code reads to become a chess tutor. Concise (~300-400 lines) with pointers to references for detailed content.

```markdown
---
name: chess-speedrun
description: >
  Adaptive chess tutor that takes a complete beginner from zero to competitive play.
  Use when the user wants to learn chess, practice chess, play a lesson, review past
  games, do tactical puzzles, or generate a study plan. Triggers include: "chess lesson",
  "let's play chess", "teach me chess", "chess practice", "my chess progress", "next
  lesson", "review my games", "tactical puzzles", "SRS review", "study plan",
  "what should I work on", or any chess-related learning request.
---

# Chess Speedrun Learning System

## Role

You are three experts in one:
1. **Grandmaster Teacher**: Deep chess knowledge, efficient skill-building, pattern-based teaching
2. **Learning Psychologist**: Zone of proximal development, cognitive load management, deliberate practice
3. **Behavioral Specialist**: Motivation, habit formation, streak psychology, dropout prevention

## Quick Start

On ANY chess-related request:

1. Read `data/progress.json` for current state (create if missing with defaults)
2. Check if MCP server is running; if not, guide user to start it
3. Load the relevant reference file based on current phase
4. Proceed with the appropriate activity

## Core Loop: Play → Analyze → Teach → Replay → Plan

### Starting a Session

1. Check `data/progress.json` for: current_elo, current_phase, current_lesson,
   streak_days, last_session_date, pending_srs_count
2. If SRS cards due > 10, suggest review first
3. Load latest lesson plan from `data/lesson_plans/` if exists
4. Launch TUI: `python scripts/tui.py` in a separate terminal
5. Begin the session activity

### During a Game

For EVERY player move:
1. Call MCP tool `evaluate_move(move)` to get cp_loss and best_move
2. If cp_loss <= 30: Brief acknowledgment, continue
3. If cp_loss 31-80: Mention the better move casually
4. If cp_loss 81-200: TEACHING MOMENT — pause, explain the mistake, show the
   pattern, offer takeback
5. If cp_loss > 200: FULL INTERVENTION — explain the tactic missed, name the
   pattern (fork/pin/skewer/etc.), create an SRS card, strongly suggest takeback

Adapt language to the player's estimated Elo:
- < 600: Use analogies, avoid jargon, focus on piece safety
- 600-1000: Introduce tactical vocabulary, explain patterns by name
- 1000-1500: Discuss positional concepts, calculation lines

### After a Game

1. Call MCP tool `get_game_pgn()` and save to `data/games/`
2. Show summary: accuracy %, blunders, critical moments
3. Identify top 3 most instructive positions
4. Ask: Replay (same position, apply lessons) or Move on?
5. On replay: increment attempt_number, same starting position
6. Track improvement across attempts

### Ending a Session

1. Save session log to `data/sessions/`
2. Update `data/progress.json`
3. Generate lesson plan for next session using 3-perspective framework
4. Save plan to `data/lesson_plans/`
5. Update streak, show motivational message if milestone approaching

## Difficulty Control

Target engine Elo = player_elo + adaptive_offset

| Player Accuracy (last 3 games) | Offset |
|-------------------------------|--------|
| < 50% (frustrated) | +50 |
| 50-60% (challenged) | +100 |
| 60-80% (sweet spot) | +150 |
| > 80% (too easy) | +200, advance lesson |

For sub-1320 Elo (Stockfish minimum): use depth limiting + random move injection.
See `scripts/engine.py` for implementation.

## SRS System

Cards are created from game mistakes. Each card = a position (FEN) + correct move.

Run `python scripts/srs.py due` to check due cards.
Run `python scripts/srs.py review` to start a review session.

SM-2 intervals: 4hr → 1d → 3d → 1wk → 2wk → 1mo
Failed cards reset to 4hr.

Present each card as: show board, ask "find the best move", check answer,
explain if wrong, update scheduling.

## Curriculum Phases

See `references/curriculum.md` for full details. Summary:

### Phase 1: Foundation (Elo 0-600, ~4-6 weeks)
Piece movement → captures → check/checkmate → special moves → piece values →
basic mates → first full games

### Phase 2: Tactical Basics (Elo 600-1000, ~8-12 weeks)
Opening principles → forks → pins → skewers → discovered attacks →
removing defender → back rank → basic pawn endgames

### Phase 3: Intermediate (Elo 1000-1500, ~16-24 weeks)
Advanced tactics → deflection/decoy → trapped pieces → mating patterns →
rook endgames → positional basics → opening repertoire → pawn structures

## 3-Perspective Lesson Plan

After each session, generate a plan considering:

**GM Teacher**: What chess knowledge gaps are critical? What patterns to drill?
Most efficient path to next +100 Elo?

**Psychologist**: Is the student in ZPD (60-80% accuracy)? Adjust difficulty?
Interleave or block practice? Cognitive load concerns?

**Behaviorist**: Motivation level? Streak health? Session length appropriate?
Approaching milestones? Habit anchor suggestions?

Synthesize into: ordered activities, time estimates, difficulty targets, focus areas.

## File References

- Detailed curriculum and lesson content → `references/curriculum.md`
- Chess teaching methodology → `references/chess-pedagogy.md`
- Tactical pattern catalog → `references/tactical-patterns.md`
- Common beginner mistakes → `references/common-mistakes.md`
- Learning science theory → `references/learning-science.md`
- Elo milestone descriptions → `references/elo-milestones.md`
- Opening recommendations → `references/opening-guide.md`
```

---

## 5. CLAUDE.md — Project instructions for Claude Code

```markdown
# Chess Speedrun Learning System

## Project Overview
This repo transforms Claude Code into an adaptive chess tutor. You ARE the tutor.
Stockfish handles analysis. The TUI handles display. You handle teaching.

## Setup
- Run `bash scripts/install.sh` to install Stockfish and Python dependencies
- Start MCP server: `cd mcp-server && python server.py`
- Launch TUI: `python scripts/tui.py` (in separate terminal)

## Key Commands
- `python scripts/engine.py analyze <fen>` — analyze a position
- `python scripts/engine.py play <elo>` — start a game at given Elo
- `python scripts/srs.py due` — check due SRS cards
- `python scripts/srs.py review` — run SRS review session
- `python scripts/export.py progress` — export progress report

## Data
All user data in `data/`. Progress in `data/progress.json`.
Games saved as PGN in `data/games/`. Session logs in `data/sessions/`.

## MCP Server
The chess engine is exposed as MCP tools. See `mcp-server/` for details.
Tools: new_game, get_board, make_move, analyze_position, get_best_move,
evaluate_move, get_game_pgn, engine_move, set_difficulty

## Teaching Approach
Read SKILL.md for the full teaching framework. Key points:
- You are 3 experts: GM teacher, learning psychologist, behavioral specialist
- Analyze EVERY move with Stockfish, teach on mistakes
- Adapt difficulty to keep accuracy at 60-80%
- Create SRS cards from blunders
- Generate 3-perspective lesson plans after each session
```

---

## 6. MCP Server specification

The MCP server wraps Stockfish and python-chess into tools that Claude Code can call natively.

### Tools

```python
# mcp-server/server.py

@server.tool()
def new_game(
    target_elo: int = 800,
    player_color: str = "white",
    starting_fen: str | None = None
) -> dict:
    """Start a new game against Stockfish at the given Elo.

    Args:
        target_elo: Engine playing strength (400-3190).
                    Below 1320, uses depth limiting + random moves.
        player_color: "white" or "black"
        starting_fen: Optional custom starting position (FEN string).
                      Use for lesson-specific positions.

    Returns:
        {game_id, board_ascii, board_fen, player_color, engine_elo, legal_moves}
    """

@server.tool()
def get_board(game_id: str) -> dict:
    """Get current board state.

    Returns:
        {board_ascii, board_fen, turn, move_number, legal_moves,
         is_check, is_checkmate, is_stalemate, result}
    """

@server.tool()
def make_move(game_id: str, move: str) -> dict:
    """Make a player move (SAN notation like 'e4', 'Nf3', 'O-O').

    Returns:
        {success, board_ascii, board_fen, move_san, move_uci,
         is_capture, is_check, is_checkmate, result}

    Raises error if move is illegal (with list of legal moves).
    """

@server.tool()
def engine_move(game_id: str) -> dict:
    """Let the engine make its move at configured difficulty.

    Returns:
        {move_san, move_uci, board_ascii, board_fen,
         is_capture, is_check, is_checkmate, result}
    """

@server.tool()
def analyze_position(
    fen: str,
    depth: int = 20,
    multipv: int = 3
) -> dict:
    """Full-strength Stockfish analysis of a position.

    Always runs at maximum strength regardless of game difficulty.

    Returns:
        {eval_cp, eval_mate, best_move, best_line,
         top_moves: [{move, score_cp, score_mate, pv_line}]}
    """

@server.tool()
def evaluate_move(game_id: str, move: str) -> dict:
    """Evaluate a specific move against the engine's best.

    This is the key teaching tool — call after every player move.

    Returns:
        {move_san, best_move_san, cp_loss, eval_before, eval_after,
         classification: "excellent"|"good"|"inaccuracy"|"mistake"|"blunder",
         is_best_move: bool,
         best_line: [moves...],
         tactical_motif: str|null}
    """

@server.tool()
def get_game_pgn(game_id: str) -> dict:
    """Export the current game as PGN with annotations.

    Returns:
        {pgn_string, moves_count, result, white, black}
    """

@server.tool()
def set_difficulty(game_id: str, target_elo: int) -> dict:
    """Change engine difficulty mid-game.

    Returns:
        {previous_elo, new_elo, method: "uci_elo"|"depth_limit"|"random_blend"}
    """

@server.tool()
def get_legal_moves(game_id: str, square: str | None = None) -> dict:
    """Get all legal moves, optionally filtered by source square.

    Useful for teaching piece movement to beginners.

    Returns:
        {moves: [{san, uci, is_capture, is_check}],
         count: int}
    """

@server.tool()
def set_position(fen: str) -> dict:
    """Set up a specific position (for puzzles/drills).

    Returns:
        {board_ascii, board_fen, turn, legal_moves}
    """

@server.tool()
def undo_move(game_id: str) -> dict:
    """Take back the last move (for teaching takebacks).

    Returns:
        {success, board_ascii, board_fen, undone_move}
    """
```

### MCP Server implementation approach

```python
# mcp-server/server.py
from mcp.server.fastmcp import FastMCP
import chess
import chess.engine
import chess.pgn
import uuid
import random
import json
from pathlib import Path

server = FastMCP("chess-engine")

# Global state
games: dict[str, dict] = {}
GAME_STATE_FILE = Path("data/current_game.json")

def get_engine_path() -> str:
    """Auto-detect Stockfish binary."""
    import shutil
    for p in [shutil.which("stockfish"), "/usr/local/bin/stockfish",
              "/usr/bin/stockfish", "/opt/homebrew/bin/stockfish"]:
        if p and Path(p).exists():
            return p
    raise FileNotFoundError("Stockfish not found. Run: bash scripts/install.sh")

def sync_tui(game_state: dict):
    """Write game state to JSON file for TUI to pick up."""
    GAME_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    GAME_STATE_FILE.write_text(json.dumps(game_state, indent=2))

def make_weak_move(board: chess.Board, engine, target_elo: int) -> chess.Move:
    """Generate a move at sub-1320 Elo using blended strategy."""
    random_prob = max(0, (1320 - target_elo) / 1320)
    if random.random() < random_prob:
        return random.choice(list(board.legal_moves))
    depth = max(1, min(5, target_elo // 300))
    result = engine.play(board, chess.engine.Limit(depth=depth))
    return result.move
```

---

## 7. Terminal UI (TUI) design

The TUI runs in a **separate terminal** and auto-updates whenever the game state changes. It communicates with the MCP server via a shared JSON state file.

### Design: Simple, functional, beginner-friendly

```
┌─── Chess Speedrun ─── Session #14 ─── 🔥 11 days ──────────┐
│                                                               │
│   Lesson: Tactical Basics — Pins (Attempt 1)                 │
│   You: White │ Engine: ~880 Elo │ Your Est. Elo: 780         │
│                                                               │
│    a   b   c   d   e   f   g   h                              │
│  ┌───┬───┬───┬───┬───┬───┬───┬───┐                           │
│ 8│ ♜ │   │ ♝ │ ♛ │ ♚ │   │   │ ♜ │ 8    Moves:             │
│  ├───┼───┼───┼───┼───┼───┼───┼───┤        1. e4  e5          │
│ 7│ ♟ │ ♟ │   │   │   │ ♟ │ ♟ │ ♟ │ 7     2. Nf3 Nc6         │
│  ├───┼───┼───┼───┼───┼───┼───┼───┤        3. d4  exd4        │
│ 6│   │   │ ♞ │   │   │ ♞ │   │   │ 6     4. Nxd4 Nf6        │
│  ├───┼───┼───┼───┼───┼───┼───┼───┤        5. Nc3  Bb4        │
│ 5│   │   │   │ ♟ │   │   │ ♗ │   │ 5     6. Bg5  ...        │
│  ├───┼───┼───┼───┼───┼───┼───┼───┤                           │
│ 4│   │   │   │ ♙ │   │   │   │   │ 4    Eval: +1.2 ▰▰▰▱▱   │
│  ├───┼───┼───┼───┼───┼───┼───┼───┤                           │
│ 3│   │   │ ♘ │   │   │ ♘ │   │   │ 3    Accuracy: 78%       │
│  ├───┼───┼───┼───┼───┼───┼───┼───┤    Blunders: 0           │
│ 2│ ♙ │ ♙ │ ♙ │   │   │ ♙ │ ♙ │ ♙ │ 2   Mistakes: 1         │
│  ├───┼───┼───┼───┼───┼───┼───┼───┤                           │
│ 1│ ♖ │   │   │ ♕ │ ♔ │ ♗ │   │ ♖ │ 1                        │
│  └───┴───┴───┴───┴───┴───┴───┴───┘                           │
│    a   b   c   d   e   f   g   h                              │
│                                                               │
│  White to move                                                │
│  💡 Tip: Your bishop on g5 is pinning the knight to the queen │
└───────────────────────────────────────────────────────────────┘
```

### Implementation: Rich + file-based sync

```python
# scripts/tui.py
"""
Chess TUI - runs in a separate terminal.
Watches data/current_game.json for state changes and re-renders.
Can also accept direct move input.

Usage:
    python scripts/tui.py                    # Watch mode (display only)
    python scripts/tui.py --interactive      # Watch + accept move input
"""

from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
import json
import time
from pathlib import Path

GAME_STATE_FILE = Path("data/current_game.json")

PIECE_SYMBOLS = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟',
}

def render_board(fen: str, last_move: str = None) -> Table:
    """Render chess board with Rich, with square colors and piece symbols."""
    # Parse FEN, create 8x8 grid with alternating dark/light squares
    # Highlight last move source/destination squares
    pass

def render_sidebar(game_state: dict) -> Panel:
    """Render move list, eval bar, accuracy stats, tips."""
    pass

def main():
    layout = Layout()
    layout.split_row(
        Layout(name="board", ratio=2),
        Layout(name="sidebar", ratio=1),
    )

    with Live(layout, refresh_per_second=4) as live:
        while True:
            if GAME_STATE_FILE.exists():
                state = json.loads(GAME_STATE_FILE.read_text())
                layout["board"].update(render_board(state["fen"], state.get("last_move")))
                layout["sidebar"].update(render_sidebar(state))
            time.sleep(0.25)
```

### Sync mechanism

The MCP server writes `data/current_game.json` after every move:

```json
{
    "game_id": "abc123",
    "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
    "last_move": "e2e4",
    "last_move_san": "e4",
    "turn": "black",
    "move_number": 1,
    "moves": ["e4"],
    "eval_cp": 20,
    "player_color": "white",
    "engine_elo": 880,
    "player_elo_estimate": 780,
    "accuracy_running": 78.5,
    "blunders": 0,
    "mistakes": 1,
    "lesson": "pins",
    "attempt": 1,
    "session": 14,
    "tip": "Your bishop on g5 is pinning the knight to the queen"
}
```

The TUI polls this file at 4Hz and re-renders. Simple, reliable, no socket complexity.

---

## 8. Data models

### progress.json

```json
{
    "user": {
        "name": "Suvojit",
        "created_at": "2025-02-06T00:00:00Z"
    },
    "elo": {
        "estimate": 780,
        "confidence": 150,
        "history": [
            {"date": "2025-02-06", "elo": 400},
            {"date": "2025-02-10", "elo": 550},
            {"date": "2025-02-20", "elo": 780}
        ]
    },
    "curriculum": {
        "current_phase": "tactical_basics",
        "current_lesson": "pins",
        "lessons_completed": [
            "piece_movement", "captures", "check_checkmate",
            "special_moves", "piece_values", "basic_mates",
            "first_games", "opening_principles", "forks"
        ],
        "phase_progress_pct": 35
    },
    "streak": {
        "current_days": 11,
        "longest_days": 11,
        "last_active": "2025-02-05"
    },
    "stats": {
        "total_games": 42,
        "total_sessions": 13,
        "total_study_minutes": 310,
        "total_puzzles_solved": 156,
        "puzzle_accuracy_pct": 72,
        "avg_game_accuracy_pct": 68,
        "blunder_rate_per_game": 1.2,
        "most_common_mistake_motif": "hanging_piece",
        "strongest_motif": "forks",
        "weakest_motif": "pins"
    },
    "srs": {
        "total_cards": 34,
        "due_now": 8,
        "mastered": 12,
        "learning": 22
    },
    "settings": {
        "session_target_minutes": 25,
        "teaching_verbosity": "normal",
        "show_eval_bar": true,
        "auto_takeback_on_blunder": false
    }
}
```

### Session log (data/sessions/session_014.json)

```json
{
    "session_id": 14,
    "date": "2025-02-05T18:30:00Z",
    "duration_minutes": 23,
    "elo_before": 750,
    "elo_after": 780,
    "activities": [
        {
            "type": "srs_review",
            "duration_min": 5,
            "cards_reviewed": 8,
            "accuracy_pct": 75,
            "failed_cards": ["card_017", "card_023"]
        },
        {
            "type": "guided_game",
            "game_file": "games/game_041.pgn",
            "lesson": "pins",
            "attempt": 1,
            "engine_elo": 880,
            "result": "1-0",
            "accuracy_pct": 68,
            "blunders": 0,
            "mistakes": 1,
            "teaching_moments": [
                {
                    "move_number": 12,
                    "played": "h3",
                    "best": "Bxf6",
                    "cp_loss": 135,
                    "motif": "pin_capture",
                    "taught": true,
                    "takeback": true
                }
            ],
            "new_srs_cards_created": 1
        },
        {
            "type": "guided_game",
            "game_file": "games/game_042.pgn",
            "lesson": "pins",
            "attempt": 2,
            "engine_elo": 880,
            "result": "1-0",
            "accuracy_pct": 81,
            "blunders": 0,
            "mistakes": 0,
            "improvement_vs_attempt_1": "+13%"
        }
    ],
    "concepts_practiced": ["pins", "forks"],
    "concepts_taught_new": ["absolute_pin", "pin_capture"],
    "summary": "Strong session. Pin capture clicked on replay. Ready to advance."
}
```

### SRS card (srs_cards.json entry)

```json
{
    "card_id": "card_035",
    "created_at": "2025-02-05T18:45:00Z",
    "source": {
        "game_id": "game_041",
        "move_number": 12,
        "mistake_type": "missed_pin_capture"
    },
    "card_type": "tactic",
    "fen": "r1bqk2r/ppp2ppp/2n2n2/3pp1B1/3PP3/2N2N2/PPP2PPP/R2QKB1R w KQkq - 0 6",
    "prompt": "White to move. How can you exploit the pin?",
    "solution_moves": ["g5f6"],
    "solution_san": ["Bxf6"],
    "motif": "pin_capture",
    "difficulty": 2,
    "explanation": "The bishop on g5 pins the knight on f6 to the queen on d8. Capturing with Bxf6 wins the knight and damages Black's pawn structure.",
    "sm2": {
        "ease_factor": 2.5,
        "interval_days": 0.167,
        "repetitions": 0,
        "next_review": "2025-02-05T22:45:00Z",
        "last_review": null
    },
    "stats": {
        "total_attempts": 0,
        "correct": 0,
        "avg_solve_time_sec": null
    },
    "tags": ["pin", "capture", "middlegame", "tactical_basics"]
}
```

---

## 9. Key scripts implementation

### scripts/engine.py — Stockfish wrapper

```python
"""
Stockfish UCI wrapper for the Chess Speedrun system.

Usage (standalone CLI):
    python scripts/engine.py analyze "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    python scripts/engine.py play 800

Usage (as module):
    from engine import ChessEngine
    engine = ChessEngine()
    engine.new_game(target_elo=800)
"""

import chess
import chess.engine
import chess.pgn
import json
import random
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass, asdict

STOCKFISH_PATHS = [
    shutil.which("stockfish"),
    "/usr/local/bin/stockfish",
    "/usr/bin/stockfish",
    "/opt/homebrew/bin/stockfish",
]

@dataclass
class MoveEvaluation:
    move_san: str
    best_move_san: str
    cp_loss: int
    eval_before: int
    eval_after: int
    classification: str  # excellent/good/inaccuracy/mistake/blunder
    is_best: bool
    best_line: list[str]
    tactical_motif: str | None = None

class ChessEngine:
    def __init__(self, stockfish_path: str | None = None):
        path = stockfish_path or self._find_stockfish()
        self.engine = chess.engine.SimpleEngine.popen_uci(path)
        self.board = chess.Board()
        self.target_elo = 800
        self.game_pgn = chess.pgn.Game()
        self.current_node = self.game_pgn

    @staticmethod
    def _find_stockfish() -> str:
        for p in STOCKFISH_PATHS:
            if p and Path(p).exists():
                return p
        raise FileNotFoundError(
            "Stockfish not found. Install: brew install stockfish (mac) "
            "or apt install stockfish (linux)"
        )

    def set_difficulty(self, target_elo: int):
        """Configure engine for gameplay at target Elo."""
        self.target_elo = target_elo
        if target_elo >= 1320:
            self.engine.configure({
                "UCI_LimitStrength": True,
                "UCI_Elo": target_elo,
            })

    def get_engine_move(self) -> chess.Move:
        """Get engine move at configured difficulty."""
        if self.target_elo >= 1320:
            result = self.engine.play(self.board, chess.engine.Limit(time=2.0))
            return result.move

        # Sub-1320: blend random moves with shallow engine
        random_prob = max(0, (1320 - self.target_elo) / 1320)
        if random.random() < random_prob:
            return random.choice(list(self.board.legal_moves))

        depth = max(1, min(5, self.target_elo // 300))
        result = self.engine.play(self.board, chess.engine.Limit(depth=depth))
        return result.move

    def analyze_position(self, depth: int = 20, multipv: int = 3) -> list[dict]:
        """Full-strength analysis (always max strength)."""
        self.engine.configure({"UCI_LimitStrength": False})
        infos = self.engine.analyse(
            self.board, chess.engine.Limit(depth=depth), multipv=multipv,
        )
        results = []
        for info in infos:
            score = info["score"].white()
            results.append({
                "move": self.board.san(info["pv"][0]),
                "move_uci": info["pv"][0].uci(),
                "score_cp": score.score(mate_score=10000),
                "score_mate": score.mate(),
                "pv_line": [self.board.san(m) for m in info["pv"][:6]],
                "depth": info["depth"],
            })
        # Restore difficulty
        if self.target_elo >= 1320:
            self.engine.configure({
                "UCI_LimitStrength": True,
                "UCI_Elo": self.target_elo,
            })
        return results

    def evaluate_move(self, move_san: str) -> MoveEvaluation:
        """Evaluate a player's move against engine's best."""
        analysis_before = self.analyze_position(depth=20, multipv=1)
        eval_before = analysis_before[0]["score_cp"]
        best_move_san = analysis_before[0]["move"]
        best_line = analysis_before[0]["pv_line"]

        move = self.board.parse_san(move_san)
        self.board.push(move)
        analysis_after = self.analyze_position(depth=20, multipv=1)
        eval_after = -analysis_after[0]["score_cp"]
        self.board.pop()

        cp_loss = max(0, eval_before - eval_after)
        is_best = move_san == best_move_san

        if cp_loss <= 10:      classification = "excellent"
        elif cp_loss <= 30:    classification = "good"
        elif cp_loss <= 80:    classification = "inaccuracy"
        elif cp_loss <= 200:   classification = "mistake"
        else:                  classification = "blunder"

        motif = self._detect_motif(best_move_san) if not is_best else None

        return MoveEvaluation(
            move_san=move_san, best_move_san=best_move_san,
            cp_loss=cp_loss, eval_before=eval_before, eval_after=eval_after,
            classification=classification, is_best=is_best,
            best_line=best_line, tactical_motif=motif,
        )

    def _detect_motif(self, best_move_san: str) -> str | None:
        """Basic tactical motif detection using attack maps."""
        # Check for forks, pins, discovered attacks after best move
        # Uses python-chess attack/pin detection APIs
        return None

    def close(self):
        self.engine.quit()
```

### scripts/srs.py — Spaced repetition manager

```python
"""
SRS (Spaced Repetition System) card manager.

Usage:
    python scripts/srs.py due           # Show count of due cards
    python scripts/srs.py review        # Interactive review session (outputs JSON)
    python scripts/srs.py add <json>    # Add a new card
    python scripts/srs.py stats         # Show SRS statistics
    python scripts/srs.py update <card_id> <quality>  # Update card after review
"""

import json, sys
from datetime import datetime, timedelta
from pathlib import Path

SRS_FILE = Path("data/srs_cards.json")

def load_cards() -> list[dict]:
    if not SRS_FILE.exists(): return []
    return json.loads(SRS_FILE.read_text())

def save_cards(cards: list[dict]):
    SRS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SRS_FILE.write_text(json.dumps(cards, indent=2))

def get_due_cards(cards: list[dict]) -> list[dict]:
    now = datetime.utcnow().isoformat()
    return [c for c in cards if c["sm2"]["next_review"] <= now]

def sm2_update(card: dict, quality: int) -> dict:
    """SM-2 algorithm. quality 0-5. Returns updated card."""
    sm2 = card["sm2"]
    if quality < 3:
        sm2["repetitions"] = 0
        sm2["interval_days"] = 0.167  # 4 hours
    else:
        if sm2["repetitions"] == 0: sm2["interval_days"] = 1
        elif sm2["repetitions"] == 1: sm2["interval_days"] = 3
        else: sm2["interval_days"] *= sm2["ease_factor"]
        sm2["repetitions"] += 1

    sm2["ease_factor"] = max(1.3,
        sm2["ease_factor"] + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    sm2["next_review"] = (datetime.utcnow() + timedelta(days=sm2["interval_days"])).isoformat()
    sm2["last_review"] = datetime.utcnow().isoformat()
    card["stats"]["total_attempts"] = card["stats"].get("total_attempts", 0) + 1
    if quality >= 3:
        card["stats"]["correct"] = card["stats"].get("correct", 0) + 1
    return card

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "due"
    cards = load_cards()

    if cmd == "due":
        due = get_due_cards(cards)
        print(json.dumps({"due_count": len(due), "total_cards": len(cards)}))

    elif cmd == "review":
        due = get_due_cards(cards)
        # Output due cards as JSON for Claude Code to present
        print(json.dumps([{
            "card_id": c["card_id"], "fen": c["fen"],
            "prompt": c["prompt"], "motif": c.get("motif"),
            "difficulty": c.get("difficulty", 1)
        } for c in due[:20]]))

    elif cmd == "update" and len(sys.argv) >= 4:
        card_id, quality = sys.argv[2], int(sys.argv[3])
        for i, c in enumerate(cards):
            if c["card_id"] == card_id:
                cards[i] = sm2_update(c, quality)
                break
        save_cards(cards)
        print(json.dumps({"updated": card_id, "quality": quality}))

    elif cmd == "add":
        new_card = json.loads(sys.argv[2])
        cards.append(new_card)
        save_cards(cards)
        print(json.dumps({"added": new_card["card_id"]}))

    elif cmd == "stats":
        due = get_due_cards(cards)
        mastered = [c for c in cards if c["sm2"]["repetitions"] >= 5]
        print(json.dumps({
            "total": len(cards), "due": len(due),
            "mastered": len(mastered), "learning": len(cards) - len(mastered),
        }))
```

### scripts/install.sh — Setup script

```bash
#!/bin/bash
set -e

echo "🏁 Chess Speedrun - Setup"
echo "========================="

# Detect OS
OS="$(uname -s)"

# Install Stockfish
if ! command -v stockfish &> /dev/null; then
    echo "📦 Installing Stockfish..."
    if [ "$OS" = "Darwin" ]; then
        brew install stockfish
    elif [ "$OS" = "Linux" ]; then
        sudo apt-get update && sudo apt-get install -y stockfish
    else
        echo "⚠️  Install Stockfish manually: https://stockfishchess.org/download/"
        exit 1
    fi
else
    echo "✅ Stockfish already installed"
fi

# Verify
stockfish <<< "uci" | head -1
echo "✅ Stockfish working"

# Install Python deps
echo "📦 Installing Python dependencies..."
if command -v uv &> /dev/null; then
    uv pip install python-chess rich textual watchdog mcp
else
    pip install python-chess rich textual watchdog mcp
fi

# Create data directories
mkdir -p data/sessions data/games data/lesson_plans

# Initialize progress if needed
if [ ! -f data/progress.json ]; then
    cat > data/progress.json << 'EOF'
{
    "user": {"name": "", "created_at": ""},
    "elo": {"estimate": 400, "confidence": 350, "history": []},
    "curriculum": {"current_phase": "foundation", "current_lesson": "piece_movement",
                   "lessons_completed": [], "phase_progress_pct": 0},
    "streak": {"current_days": 0, "longest_days": 0, "last_active": ""},
    "stats": {"total_games": 0, "total_sessions": 0, "total_study_minutes": 0,
              "total_puzzles_solved": 0, "puzzle_accuracy_pct": 0,
              "avg_game_accuracy_pct": 0, "blunder_rate_per_game": 0},
    "srs": {"total_cards": 0, "due_now": 0, "mastered": 0, "learning": 0},
    "settings": {"session_target_minutes": 25, "teaching_verbosity": "normal"}
}
EOF
    echo "✅ Initialized progress.json"
fi

[ ! -f data/srs_cards.json ] && echo "[]" > data/srs_cards.json && echo "✅ Initialized SRS deck"

echo ""
echo "🎉 Setup complete!"
echo "Open this repo in Claude Code and say: 'Let's start my first chess lesson'"
```

---

## 10. Example Claude Code interaction flows

### First ever session

```
User: Let's start learning chess

Claude Code: *reads SKILL.md, checks data/progress.json — name empty, elo 400*

Welcome to Chess Speedrun! 🏁 I'll be your personal chess coach.

Since you're starting from scratch, let's begin with the absolute basics.
First, what should I call you?

User: Suvojit

Claude Code: *updates progress.json, launches TUI in side terminal*

Alright Suvojit! I've opened a chessboard in your other terminal.

Chess is played on an 8x8 board. White always moves first. Let me show
you how each piece moves — we'll start with the Rook.

*calls: set_position("8/8/8/4R3/8/8/8/8 w - - 0 1")*

See the Rook on e5? It moves in straight lines — up, down, left, right —
as far as it wants until it hits something. Try moving it anywhere.

User: e8

Claude Code: *calls: make_move("Re8")* ✓

The rook slides 3 squares up to e8. Now try moving it sideways.

[...continues through all pieces, then first game...]
```

### Mid-session teaching moment

```
User: I'll play h3

Claude Code: *calls: evaluate_move(game_id="g41", move="h3")*
*Result: cp_loss=135, best="Bxf6", classification="mistake", motif="pin_capture"*

Wait — that's a mistake! Look at your bishop on g5.

It's staring at the knight on f6, and behind that knight? Black's queen on d8.
That knight is **pinned** — it literally can't move without exposing the queen.

The best move is **Bxf6** — just capture the pinned knight! Black has to
recapture, and you've won a piece.

💡 **Pin Rule**: When you're pinning something, ask: "Should I just take it?"

Want to take back h3 and try Bxf6?

User: Yes, Bxf6

Claude Code: *calls undo_move, then make_move("Bxf6")*
*Creates SRS card, saves to srs_cards.json*

Excellent! That's the pin capture pattern — I've added it to your review
deck. You'll see this position again tomorrow.
```

### Session end and lesson plan

```
User: I'm done for today

Claude Code: *saves session log, updates progress, generates plan*

Great session, Suvojit! Here's your summary:

📊 **Session #14 Stats**
- SRS Review: 8 cards, 75% accuracy
- Games: 2 played (2 wins as White)
- Accuracy: 68% → 81% on replay (+13%)
- New Elo Estimate: 810 (+30) ⬆
- 🔥 Day 12 streak!

**Your plan for next time:**

♔ *GM perspective*: Pins are clicking. Next up: rook pins on open files,
then introduce skewers. Drill 10 back-rank awareness puzzles — you missed
one today.

🧠 *Psychologist*: 81% on replay = strong transfer. Bump engine to 920.
Start mixing fork + pin puzzles in SRS review.

🎯 *Behaviorist*: 12-day streak, 3-4 sessions from 1000 Elo milestone!
Keep sessions at 25 min. Start with SRS review right after your morning
coffee to lock in the habit.

*saves plan to data/lesson_plans/plan_015.json*

See you tomorrow! 👋
```

---

## 11. Development plan

### Phase 1: Foundation (Week 1)
- `scripts/install.sh` — Stockfish + deps installer
- `scripts/engine.py` — Stockfish wrapper with difficulty control + sub-1320 blending
- `mcp-server/server.py` — MCP server with core tools
- `scripts/tui.py` — Basic Rich board display with JSON file sync
- `CLAUDE.md` + initial `data/progress.json`
- **Test**: Claude Code can start a game, make moves, see analysis via MCP

### Phase 2: Teaching intelligence (Week 2)
- `SKILL.md` — Full skill file with teaching framework
- `references/curriculum.md`, `chess-pedagogy.md`, `tactical-patterns.md`, `common-mistakes.md`
- Motif detection in engine.py
- **Test**: Claude Code identifies mistakes, explains them, offers takebacks

### Phase 3: SRS and curriculum (Week 3)
- `scripts/srs.py` — Full SM-2 implementation
- `puzzles/` — Curated puzzle sets (50+ positions per motif)
- `references/learning-science.md`
- Difficulty adapter logic, lesson advancement criteria
- **Test**: SRS review works, cards auto-created from mistakes

### Phase 4: Session management (Week 4)
- Session logging (auto-save to data/sessions/)
- Progress tracking and Elo estimation
- 3-perspective lesson plan generation
- Replay mechanics, streak tracking
- **Test**: Full session flow end-to-end

### Phase 5: Polish (Week 5)
- TUI improvements (eval bar, move highlights, better styling)
- `scripts/export.py` — Progress reports
- Edge case handling
- Package as .skill file
- README with setup guide

---

## 12. Critical implementation notes

### Sub-1320 Elo — the beginner problem

Stockfish's minimum UCI_Elo is 1320. True beginners play at 400-800. Blended approach:

| Target Elo | Random Move % | Engine Depth |
|-----------|--------------|--------------|
| 400-600 | 50-70% | 1-2 |
| 600-800 | 30-50% | 2-3 |
| 800-1000 | 10-30% | 3-5 |
| 1000-1320 | 0-10% | 5-8 |
| 1320+ | 0% | Stockfish UCI_Elo natively |

### TUI sync: why file polling, not sockets

For a chess game, 250ms latency (4Hz polling) is imperceptible. File-based sync means: no socket errors, no connection management, works across terminals trivially, easy to debug (just `cat data/current_game.json`). The TUI is a display-only view by default — Claude Code handles all game logic.

### Why MCP server instead of direct bash calls

Claude Code could call `python scripts/engine.py` via bash each time, but MCP is better because:
1. **Persistent Stockfish process** — no 100ms startup per move
2. **Stateful games** — board state in memory, not reloaded from files
3. **Typed tool schemas** — Claude Code gets proper tool descriptions
4. **Future extensibility** — add Lichess API tools, puzzle database tools

### Claude Code as the intelligence layer

All teaching, curriculum management, and planning happens through Claude Code's natural reasoning. The SKILL.md provides the framework; Claude Code:
- Decides what to teach based on patterns it observes in mistakes
- Adapts language complexity to the player's level
- Reasons through three expert perspectives for lesson planning
- Creates SRS cards with contextual explanations
- Manages motivation, streaks, and engagement

This is fundamentally more flexible than any prompt-engineered API approach.
