# Chess Speedrun Learning System - Canonical Feature Documentation

## Overview

An adaptive chess tutor system where Claude Code acts as a teaching intelligence, Stockfish provides chess analysis via an MCP server, a Rich-based TUI displays the board in the terminal, and a spaced repetition system tracks mistakes for review.

**Problem:** Learning chess lacks personalized, adaptive tutoring that adjusts difficulty and teaching style to the learner's level. Existing tools are either too simple (static puzzles) or too complex (raw engine analysis).

**Consumer:**
- **Primary:** Chess learners using Claude Code as their tutor
- **Secondary:** The ralph loop (autonomous agent) that implements the system story-by-story

**Success criteria:** All 13 stories implemented, each passing acceptance criteria, the system functions end-to-end: a user can play against Stockfish at an adaptive difficulty, see the board in a TUI, get teaching feedback from Claude, and review mistakes via SRS.

## Scope

### In Scope
- Stockfish engine wrapper with adaptive difficulty (Elo 400-3000+)
- MCP server exposing 12 chess tools to Claude Code
- Rich-based terminal UI with auto-updating board display
- SM-2 spaced repetition for mistake tracking
- SKILL.md tutor personality and methodology
- Reference documentation (curriculum, pedagogy, tactics, mistakes, openings)
- Curated puzzle sets by tactical motif
- Progress export as markdown reports
- Project setup with uv environment management

### Out of Scope
- Web UI or GUI (terminal only)
- Online play (local Stockfish only)
- Multi-player support
- Database storage (JSON files only)
- Automated Elo rating calculation for the player
- Opening book integration
- Endgame tablebase integration

## Process Flow

```
US-001: Project Structure + Install
    |
US-002: Engine Wrapper (+ pytest)
    |
US-003: SRS Manager (+ pytest)
    |
US-004: MCP Server - Core Game Tools
    |
US-005: MCP Server - Analysis Tools
    |
US-006: MCP Server - Utility Tools
    |
US-007: Terminal UI
    |
US-008: Reference Docs - Curriculum & Pedagogy
    |
US-009: Reference Docs - Tactics & Mistakes
    |
US-010: Puzzle Sets
    |
US-011: SKILL.md Tutor Skill File
    |
US-012: Export Script
    |
US-013: Claude Settings + Integration Test
```

**Key dependency:** Each story depends on the one above it. The ralph loop processes them in order, one per iteration.

**Decision point:** If a story fails, the ralph loop retries it in the next iteration. No branching - strictly sequential.

## Story Details

---

### US-001: Create Install Script and Project Structure

**Purpose:** Bootstrap the project so all subsequent stories have a working environment.

**Files created:**
- `scripts/install.sh` (executable)
- `scripts/models.py` (shared dataclasses: GameState, MoveEvaluation)
- `pyproject.toml` (project metadata, dependencies)
- `data/` directory structure: `data/sessions/`, `data/games/`, `data/lesson_plans/`
- `data/progress.json` (default values if not exists)
- `data/srs_cards.json` (empty array if not exists)
- `data/.gitkeep` files

**install.sh behavior:**
1. Detect OS (macOS vs Linux)
2. Install Stockfish via `brew install stockfish` (macOS) or `apt install stockfish` (Linux)
3. Install `uv` if not present
4. Create/sync project environment with `uv sync` or `uv pip install`
5. Python deps: `python-chess`, `rich`, `textual`, `watchdog`, `mcp[cli]`
6. Create data directories if they don't exist
7. Initialize `data/progress.json` with defaults if not exists
8. Initialize `data/srs_cards.json` as `[]` if not exists

**scripts/models.py contents:**
```python
@dataclass
class GameState:
    game_id: str
    fen: str
    board_display: str  # Unicode board string
    move_list: list[str]  # SAN moves
    last_move: str | None  # e.g., "e2e4"
    last_move_san: str | None
    eval_score: float | None  # centipawns from white's perspective
    player_color: str  # "white" or "black"
    target_elo: int
    is_game_over: bool
    result: str | None  # "1-0", "0-1", "1/2-1/2"
    legal_moves: list[str]
    accuracy: dict  # {"white": float, "black": float}
    session_number: int
    streak: int
    lesson_name: str

@dataclass
class MoveEvaluation:
    move_san: str
    best_move_san: str
    cp_loss: int
    eval_before: float
    eval_after: float
    classification: str  # "brilliant", "great", "good", "inaccuracy", "mistake", "blunder"
    is_best: bool
    best_line: list[str]
    tactical_motif: str | None  # None for now, future enhancement
```

**pyproject.toml:**
- Project name: `chess-speedrun`
- Python: `>=3.10`
- Dependencies: `python-chess`, `rich`, `textual`, `watchdog`, `mcp[cli]`
- Dev dependencies: `pytest`

**Acceptance criteria:**
- `scripts/install.sh` exists and is executable
- `pyproject.toml` exists with correct metadata and deps
- `scripts/models.py` exists with GameState and MoveEvaluation dataclasses
- Data directories exist: `data/sessions/`, `data/games/`, `data/lesson_plans/`
- `data/progress.json` initialized with defaults
- `data/srs_cards.json` initialized as `[]`
- `python -m py_compile scripts/models.py` passes
- `python -c "from scripts.models import GameState, MoveEvaluation"` passes

**Edge cases:**
- Stockfish already installed: skip installation, don't error
- Data files already exist: don't overwrite
- No brew/apt available: print clear error with manual install instructions
- uv not installed: install uv first via `curl -LsSf https://astral.sh/uv/install.sh | sh`

---

### US-002: Implement Stockfish Engine Wrapper

**Purpose:** Python wrapper around Stockfish for game play and analysis with adaptive difficulty.

**Files created:**
- `scripts/engine.py` (ChessEngine class + CLI)
- `tests/test_engine.py` (pytest tests)

**ChessEngine class API:**
```python
class ChessEngine:
    def __init__(self, stockfish_path: str | None = None):
        """Auto-detect Stockfish if path not given. Raise clear error if not found."""

    def new_game(self, target_elo: int = 800, player_color: str = "white", starting_fen: str | None = None) -> chess.Board:
        """Start new game. Configure engine difficulty."""

    def set_difficulty(self, target_elo: int) -> None:
        """Configure engine strength. Sub-1320 uses depth+random blend."""

    def get_engine_move(self, board: chess.Board) -> chess.Move:
        """Get engine move at configured difficulty."""

    def analyze_position(self, board: chess.Board, depth: int = 20, multipv: int = 3) -> list[dict]:
        """Full-strength analysis regardless of difficulty setting."""

    def evaluate_move(self, board: chess.Board, move: chess.Move) -> MoveEvaluation:
        """Compare player move to best move. Returns MoveEvaluation dataclass."""

    def close(self):
        """Clean up Stockfish process."""
```

**Difficulty model (sub-1320 Elo):**
- Linear scale blending random moves with low-depth engine moves
- Elo 400: 70% random legal moves, 30% engine at depth 1
- Elo 600: 55% random, 45% engine at depth 2
- Elo 800: 40% random, 60% engine at depth 3
- Elo 1000: 25% random, 75% engine at depth 4
- Elo 1200: 10% random, 90% engine at depth 5
- Elo 1320+: 0% random, use UCI_Elo setting directly
- Formula: `random_pct = max(0, 0.85 - (elo / 1320) * 0.85)`
- Depth: `depth = max(1, min(5, elo // 250))`

**Move classification thresholds (cp_loss):**
- 0: "brilliant" or "best" (is_best=True)
- 1-30: "great"
- 31-80: "good"
- 81-150: "inaccuracy"
- 151-300: "mistake"
- 300+: "blunder"

**CLI interface:**
- `python scripts/engine.py analyze <fen>` - Analyze position, print top 3 lines
- `python scripts/engine.py play <elo>` - One-move demo: setup board, engine plays one move, print result
- `python scripts/engine.py play <elo> --interactive` - Full game loop: prompt for moves, engine responds, until game over

**Acceptance criteria:**
- `scripts/engine.py` exists with ChessEngine class
- Auto-detects Stockfish binary (checks common paths: `/usr/local/bin/stockfish`, `/usr/bin/stockfish`, `/opt/homebrew/bin/stockfish`, `which stockfish`)
- `new_game()` starts game with configurable Elo
- `set_difficulty()` configures engine strength with linear blend for sub-1320
- `get_engine_move()` returns legal move at configured difficulty
- `analyze_position()` runs full-strength analysis with multipv
- `evaluate_move()` returns MoveEvaluation with cp_loss and classification
- CLI `analyze` and `play` commands work
- `python -m py_compile scripts/engine.py` passes
- `python -c "from scripts.engine import ChessEngine"` passes
- `python -m pytest tests/test_engine.py` passes (tests for: difficulty config, move classification, FEN analysis)

**Edge cases:**
- Stockfish not found: raise `FileNotFoundError` with message "Stockfish not found. Run scripts/install.sh first."
- Invalid FEN: raise `ValueError` with descriptive message
- Game already over: `get_engine_move()` raises `ValueError("Game is already over")`
- Invalid move in evaluate: raise `ValueError`
- Stockfish process crashes: catch `chess.engine.EngineTerminatedError`, attempt restart once

**Test coverage (pytest):**
- Test difficulty configuration at various Elo levels
- Test move classification thresholds
- Test FEN analysis returns expected structure
- Test new_game initializes correctly
- Test sub-1320 blend produces legal moves
- Mock Stockfish for unit tests (don't require actual binary in CI)

---

### US-003: Implement SRS Spaced Repetition Manager

**Purpose:** SM-2 algorithm implementation for tracking chess mistakes and scheduling reviews.

**Files created:**
- `scripts/srs.py` (SRS manager + CLI)
- `tests/test_srs.py` (pytest tests)

**Data schema (srs_cards.json):**
```json
[
  {
    "id": "uuid-string",
    "fen": "rnbqkbnr/...",
    "player_move": "e4",
    "best_move": "d4",
    "cp_loss": 45,
    "classification": "inaccuracy",
    "motif": null,
    "explanation": "d4 controls the center more effectively",
    "created_at": "2024-01-15T10:30:00Z",
    "next_review": "2024-01-15T14:30:00Z",
    "interval_hours": 4,
    "ease_factor": 2.5,
    "repetitions": 0,
    "quality_history": []
  }
]
```

**SM-2 algorithm:**
- Intervals: 4hr -> 1d -> 3d -> 1wk -> 2wk -> 1mo (in hours: 4, 24, 72, 168, 336, 720)
- Quality scale: 0-5 (0=complete blackout, 5=perfect recall)
- Failed (quality < 3): reset to 4hr interval, repetitions = 0
- Passed (quality >= 3): advance to next interval
- Ease factor: `EF' = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))`, minimum 1.3
- After interval 6 (1mo), multiply previous interval by ease_factor

**Timestamps:** ISO 8601 strings (e.g., `"2024-01-15T10:30:00Z"`)

**CLI commands (all output JSON):**
- `python scripts/srs.py due` - List cards where `next_review <= now`
- `python scripts/srs.py review <card_id> <quality>` - Update card with review result
- `python scripts/srs.py add --fen <fen> --player-move <move> --best-move <move> --cp-loss <n> --classification <class>` - Add new card
- `python scripts/srs.py stats` - Show stats: total cards, due cards, average ease factor, cards by classification

**Acceptance criteria:**
- `scripts/srs.py` exists with SM-2 implementation
- CLI commands: due, review, add, stats (all output JSON)
- Cards stored in `data/srs_cards.json`
- SM-2 intervals correct: 4hr -> 1d -> 3d -> 1wk -> 2wk -> 1mo
- Failed cards (quality < 3) reset to 4hr
- Ease factor minimum 1.3
- `get_due_cards()` returns cards where `next_review <= now`
- `sm2_update()` correctly updates interval, ease_factor, repetitions
- `python -m py_compile scripts/srs.py` passes
- `python -c "from scripts.srs import SRSManager"` passes
- `python -m pytest tests/test_srs.py` passes

**Edge cases:**
- Empty card file: return empty list for `due`, zero stats
- Card not found for review: raise `ValueError` with card ID
- Quality out of range (not 0-5): raise `ValueError`
- Corrupted JSON file: attempt to read, if fails, back up corrupted file and start fresh with `[]`
- Concurrent access: not handled in v1 (single user assumption)

**Test coverage (pytest):**
- Test SM-2 interval progression (4hr -> 1d -> 3d -> etc.)
- Test failed card resets to 4hr
- Test ease factor calculation and minimum bound
- Test due card filtering by timestamp
- Test add/review/stats CLI commands
- Test with empty card file

---

### US-004: MCP Server - Core Game Tools

**Purpose:** FastMCP server with the core game loop tools that Claude Code calls to play chess.

**Files created/modified:**
- `mcp-server/server.py` (new - FastMCP server)
- `mcp-server/requirements.txt` (new - dependencies)

**Server setup:**
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("chess-speedrun")
```

**Tools in this story (4):**
1. `new_game(target_elo: int = 800, player_color: str = "white", starting_fen: str | None = None) -> dict` - Start game, configure engine, return initial board state as GameState dict
2. `get_board(game_id: str) -> dict` - Return current GameState dict with board, legal moves, eval
3. `make_move(game_id: str, move: str) -> dict` - Player makes move (SAN notation), return updated GameState
4. `engine_move(game_id: str) -> dict` - Engine makes its move, return updated GameState

**Game state management:**
- Games stored in memory as dict keyed by `game_id`
- `game_id` is a UUID generated on `new_game()`
- Each game has: `ChessEngine` instance, `chess.Board`, metadata
- After every `make_move()` and `engine_move()`, write `data/current_game.json` using GameState dataclass

**current_game.json sync:**
- Written after EVERY move (make_move and engine_move)
- Uses `GameState` dataclass from `scripts/models.py`
- `json.dumps()` with `default=str` for serialization
- File write is atomic: write to temp file, then `os.replace()`

**Acceptance criteria:**
- `mcp-server/server.py` exists using FastMCP
- `mcp-server/requirements.txt` lists: `mcp[cli]`, `python-chess`
- Tool: `new_game` starts game, returns board state dict
- Tool: `get_board` returns current board state
- Tool: `make_move` accepts SAN notation, returns updated state
- Tool: `engine_move` makes engine move, returns updated state
- Game state synced to `data/current_game.json` after every move
- `python -m py_compile mcp-server/server.py` passes
- `python -c "import mcp.server.fastmcp"` passes

**Edge cases:**
- Invalid game_id: return error dict `{"error": "Game not found: <id>"}`
- Invalid move (not legal): return error dict `{"error": "Illegal move: <move>. Legal moves: <list>"}`
- Move when game is over: return error dict `{"error": "Game is already over. Result: <result>"}`
- Move when it's not player's turn: return error with whose turn it is
- `data/` directory doesn't exist: create it on first write

---

### US-005: MCP Server - Analysis Tools

**Purpose:** Add analysis and evaluation tools to the existing MCP server.

**Files modified:**
- `mcp-server/server.py` (add 3 tools)

**Tools in this story (3):**
1. `analyze_position(fen: str, depth: int = 20, multipv: int = 3) -> dict` - Full-strength analysis of any position
2. `evaluate_move(game_id: str, move: str) -> dict` - Evaluate a move's quality, return MoveEvaluation dict
3. `set_difficulty(game_id: str, target_elo: int) -> dict` - Change engine difficulty mid-game

**analyze_position details:**
- Does NOT require an active game - works on any FEN
- Creates temporary ChessEngine for analysis
- Returns: `{"fen": str, "depth": int, "lines": [{"rank": int, "score_cp": int, "moves": [str], "mate_in": int|None}]}`

**evaluate_move details:**
- Requires active game (game_id)
- Evaluates move WITHOUT making it (peek, don't commit)
- Returns MoveEvaluation as dict

**set_difficulty details:**
- Changes target Elo on active game
- Returns confirmation with new difficulty settings

**Acceptance criteria:**
- `analyze_position` tool works on arbitrary FEN strings
- `evaluate_move` returns MoveEvaluation with cp_loss and classification
- `set_difficulty` changes engine strength mid-game
- `python -m py_compile mcp-server/server.py` passes

**Edge cases:**
- Invalid FEN in analyze_position: return error dict
- evaluate_move on game that's over: return error
- set_difficulty with Elo < 100 or > 3500: clamp to valid range

---

### US-006: MCP Server - Utility Tools

**Purpose:** Add remaining utility tools to the MCP server.

**Files modified:**
- `mcp-server/server.py` (add 5 tools)

**Tools in this story (5):**
1. `get_game_pgn(game_id: str) -> dict` - Export game as PGN string
2. `get_legal_moves(game_id: str, square: str | None = None) -> dict` - List legal moves, optionally filtered by square
3. `undo_move(game_id: str) -> dict` - Take back last move (pops from move stack)
4. `set_position(fen: str) -> dict` - Create new game from custom position (for puzzles)
5. `srs_add_card(game_id: str, move: str, explanation: str) -> dict` - Add current position to SRS as mistake card

**Note:** `srs_add_card` is a bonus tool not in the original PRD but needed for the tutor to save mistakes to SRS during games. It calls `scripts/srs.py` internally.

**undo_move details:**
- Pops last move from board
- If last TWO moves were (player + engine), undo both to return to player's turn
- Updates `current_game.json`
- Returns updated GameState

**set_position details:**
- Creates a new game_id with the given FEN
- Engine difficulty defaults to full strength (analysis mode)
- Useful for puzzle training

**Acceptance criteria:**
- `get_game_pgn` returns valid PGN string
- `get_legal_moves` returns move list, filterable by square
- `undo_move` takes back move(s) and updates state
- `set_position` creates game from custom FEN
- `srs_add_card` saves mistake to SRS cards
- `python -m py_compile mcp-server/server.py` passes

**Edge cases:**
- undo_move on empty game (no moves): return error
- get_legal_moves on empty square: return empty list
- set_position with invalid FEN: return error
- PGN of game with no moves: return valid but minimal PGN

---

### US-007: Terminal UI with Rich

**Purpose:** Auto-updating terminal chess board display that reads from `current_game.json`.

**Files created:**
- `scripts/tui.py` (Rich-based TUI)
- `data/sample_game.json` (sample game state for testing)

**Display layout:**
```
+---------------------------+------------------+
|                           |  Session #1      |
|    8 r n b q k b n r     |  Streak: 5       |
|    7 p p p p p p p p     |  Opening Basics   |
|    6 . . . . . . . .     |                  |
|    5 . . . . . . . .     |  Moves:          |
|    4 . . . . P . . .     |  1. e4 e5        |
|    3 . . . . . . . .     |  2. Nf3 Nc6      |
|    2 P P P P . P P P     |                  |
|    1 R N B Q K B N R     |  Eval: +0.3      |
|      a b c d e f g h     |  Accuracy: 85%   |
|                           |                  |
+---------------------------+------------------+
     Board (ratio 2)         Sidebar (ratio 1)
```

**Board rendering:**
- Unicode piece symbols: `{'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙', 'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'}`
- Alternating square colors: light (`on grey85`) and dark (`on grey50`)
- Last move squares highlighted (e.g., `on yellow`)
- Board orientation: flip if player is black

**Sidebar content (from GameState):**
- Header: session number, streak, lesson name
- Move list: numbered moves in SAN
- Eval bar: visual bar + centipawn score
- Accuracy: white and black accuracy percentages

**File watching:**
- Use `watchdog` library to watch `data/current_game.json`
- Poll/check at 4Hz (250ms interval)
- On file change: re-read JSON, re-render display
- Graceful handling of partial writes (JSON parse error → skip, wait for next poll)

**CLI flags:**
- `python scripts/tui.py` - Watch mode (default), auto-updates from current_game.json
- `python scripts/tui.py --interactive` - Direct move input mode (future, not required for this story)
- `python scripts/tui.py --sample` - Display sample_game.json for testing

**Standalone testing:**
- `data/sample_game.json` contains a valid GameState with a mid-game position
- `python scripts/tui.py --sample` renders the sample and exits (no watch loop)
- This allows testing without MCP server running

**Acceptance criteria:**
- `scripts/tui.py` exists using Rich
- Renders chess board with Unicode pieces
- Alternating square colors
- Highlights last move
- Sidebar shows: move list, eval, accuracy, header info
- Watches `data/current_game.json` at ~4Hz
- `python scripts/tui.py --sample` renders sample board and exits
- `python -m py_compile scripts/tui.py` passes
- `python -c "from scripts.tui import render_board"` passes

**Edge cases:**
- `current_game.json` doesn't exist: show "Waiting for game..." message
- `current_game.json` is empty or corrupt: show last valid state, or "Waiting..."
- Terminal too small: Rich handles wrapping, but minimum 60 columns recommended
- Game over state: show result prominently

---

### US-008: Curriculum and Pedagogy Reference Files

**Purpose:** Reference materials for curriculum structure and teaching methodology.

**Files created:**
- `references/curriculum.md` - Full curriculum with phases, lessons, prerequisites
- `references/chess-pedagogy.md` - GM coaching methodology
- `references/learning-science.md` - Deliberate practice and ZPD theory
- `references/elo-milestones.md` - Skills per Elo range

**Curriculum phases:**
1. **Foundation (0-600 Elo):** Board setup, piece movement, basic checkmates, simple tactics
2. **Tactical Basics (600-1000 Elo):** Forks, pins, skewers, basic openings, endgame fundamentals
3. **Intermediate (1000-1500 Elo):** Positional play, pawn structure, complex tactics, opening repertoire

**Each file must have:**
- Clear section headers
- Substantive content (not just bullet points)
- Cross-references to other reference files where relevant

**Acceptance criteria:**
- All 4 files exist in `references/`
- `references/curriculum.md`: has Foundation, Tactical Basics, Intermediate phases with lessons
- `references/chess-pedagogy.md`: has GM coaching methodology content
- `references/learning-science.md`: has deliberate practice and ZPD content
- `references/elo-milestones.md`: has skills per Elo range (at least 0-600, 600-1000, 1000-1500)
- Each file has at least 3 major sections with headers

**Edge cases:** None - these are static content files.

---

### US-009: Tactical Patterns and Mistakes Reference Files

**Purpose:** Reference materials for tactical patterns and common beginner mistakes.

**Files created:**
- `references/tactical-patterns.md` - Motif catalog
- `references/common-mistakes.md` - Beginner mistake patterns
- `references/opening-guide.md` - Beginner-friendly opening recommendations

**Tactical patterns must include:**
- Forks (knight fork, queen fork, pawn fork)
- Pins (absolute pin, relative pin)
- Skewers
- Discovered attacks / discovered check
- Double check
- Back-rank threats
- Each with: name, description, recognition cues, teaching approach

**Common mistakes must include:**
- Hanging pieces (leaving pieces undefended)
- Ignoring opponent threats
- Premature queen development
- Not castling / king safety
- Moving same piece twice in opening
- Not controlling the center
- Each with: description, why beginners do it, teaching response

**Acceptance criteria:**
- All 3 files exist in `references/`
- `references/tactical-patterns.md`: covers forks, pins, skewers, discovered attacks at minimum
- `references/common-mistakes.md`: covers hanging pieces, ignoring threats, premature queen at minimum
- `references/opening-guide.md`: has at least 3 beginner-friendly openings with explanations
- Each pattern/mistake has: name, description, and teaching approach

**Edge cases:** None - static content files.

---

### US-010: Curated Puzzle Sets

**Purpose:** Puzzle positions organized by tactical motif for training.

**Files created:**
- `puzzles/forks.json` (10+ puzzles)
- `puzzles/pins.json` (10+ puzzles)
- `puzzles/skewers.json` (10+ puzzles)
- `puzzles/back-rank.json` (10+ puzzles)
- `puzzles/checkmate-patterns.json` (10+ puzzles)
- `puzzles/beginner-endgames.json` (10+ puzzles)
- `scripts/validate_puzzles.py` (validation script)

**Puzzle schema:**
```json
{
  "fen": "r1bqkb1r/pppppppp/2n2n2/8/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
  "solution_moves": ["e4d5", "c6d4"],
  "solution_san": ["d5", "Nxd4"],
  "motif": "fork",
  "difficulty": "beginner",
  "explanation": "The knight on d4 forks the queen on d1 and the rook on a1."
}
```

**Validation script (`scripts/validate_puzzles.py`):**
- Loads each puzzle JSON file
- Validates each FEN with `chess.Board(fen)` - must not raise
- Validates solution_moves are legal from the position
- Prints pass/fail per file
- Exit code 0 if all pass, 1 if any fail

**Acceptance criteria:**
- All 6 puzzle JSON files exist with 10+ puzzles each
- Each puzzle has: fen, solution_moves, solution_san, motif, difficulty, explanation
- `scripts/validate_puzzles.py` exists and runs
- `python scripts/validate_puzzles.py` exits with code 0 (all FENs valid, all solutions legal)
- `python -m py_compile scripts/validate_puzzles.py` passes

**Edge cases:**
- FEN validation: must produce valid chess.Board (no exceptions)
- Solution moves: must be legal from the given FEN
- Solution moves applied in sequence must each be legal after the previous

---

### US-011: SKILL.md Chess Tutor Skill File

**Purpose:** The skill file that transforms Claude Code into an adaptive chess tutor.

**Files created:**
- `SKILL.md`

**Required sections:**
1. **Frontmatter:** name, description, triggers (e.g., "chess", "play chess", "chess lesson")
2. **Expert Roles:** GM Teacher, Learning Psychologist, Behavioral Specialist
3. **Quick Start Flow:** read progress → check MCP → load references → proceed
4. **Core Loop:** Play -> Analyze -> Teach -> Replay -> Plan
5. **Move Evaluation Thresholds:** <=30 acknowledge, 31-80 mention, 81-200 teach, >200 intervene
6. **Language Adaptation:** by Elo range (<600 simple, 600-1000 moderate, 1000-1500 technical)
7. **Post-Game Flow:** save PGN, summary, teaching positions, offer replay
8. **Session Ending:** save log, update progress, 3-perspective plan
9. **Difficulty Control:** accuracy vs offset mapping table
10. **SRS Documentation:** SM-2 intervals and review process
11. **Curriculum Phases:** summary referencing `references/curriculum.md`
12. **3-Perspective Lesson Plan:** GM, Psychologist, Behaviorist framework
13. **File References:** pointing to `references/`, `puzzles/`, `data/` directories

**SKILL.md can now reference actual files** because refs (US-008, 009) and puzzles (US-010) are already created.

**Acceptance criteria:**
- `SKILL.md` exists with proper frontmatter
- Defines 3 expert roles
- Documents Quick Start, core loop, move thresholds, language adaptation
- Documents post-game flow, session ending, difficulty control
- Documents SRS system, curriculum phases, lesson plan framework
- File references section points to actual existing files
- All 13 required sections present with substantive content

**Edge cases:** None - static content file. References should use relative paths.

---

### US-012: Export Script

**Purpose:** Export progress reports and game summaries as markdown.

**Files created:**
- `scripts/export.py`

**CLI commands:**
- `python scripts/export.py progress` - Export progress report from `data/progress.json`
- `python scripts/export.py games` - Export game summaries from `data/sessions/` and `data/games/`

**Progress report output (markdown):**
```markdown
# Chess Speedrun Progress Report

## Current Level
- Estimated Elo: 650
- Sessions completed: 12
- Current streak: 5

## Accuracy Trends
- Last 5 games average: 72%
- Best game: 89%

## Areas for Improvement
- Tactics: fork recognition
- Endgame: king + pawn endings

## SRS Review Status
- Total cards: 24
- Due for review: 8
- Average ease factor: 2.3
```

**Games report output (markdown):**
```markdown
# Game Summaries

## Game 1 - 2024-01-15
- Opponent Elo: 800
- Result: Win (1-0)
- Accuracy: 78%
- Key mistakes: Nf3 (blunder, -300cp)
```

**Acceptance criteria:**
- `scripts/export.py` exists
- CLI commands: `progress` and `games`
- Reads from `data/progress.json` and `data/sessions/`
- Outputs markdown format to stdout
- `python -m py_compile scripts/export.py` passes
- `python -c "from scripts.export import export_progress, export_games"` passes

**Edge cases:**
- No progress file: print "No progress data found. Play some games first!"
- No game files: print "No games found."
- Corrupted JSON: skip corrupted files, print warning

---

### US-013: Claude Settings and Integration Verification

**Purpose:** Configure Claude Code to use the MCP server and verify end-to-end integration.

**Files created:**
- `.claude/settings.json`

**.claude/settings.json content:**
```json
{
  "mcpServers": {
    "chess-speedrun": {
      "command": "python",
      "args": ["mcp-server/server.py"],
      "env": {}
    }
  }
}
```

**Integration verification:**
- Verify all Python files pass syntax check
- Verify all imports resolve
- Verify puzzle validation passes
- Verify project structure is complete

**Acceptance criteria:**
- `.claude/settings.json` exists with MCP server config
- MCP config command points to `mcp-server/server.py`
- `python -m py_compile` passes on ALL `.py` files in the project
- `python scripts/validate_puzzles.py` passes
- All required directories exist
- All required files exist (spot check)

**Edge cases:**
- `.claude/` directory doesn't exist: create it
- `settings.json` already exists: merge, don't overwrite

---

## Error Handling Summary

| Component | Error Type | Handling |
|-----------|-----------|----------|
| engine.py | Stockfish not found | `FileNotFoundError` with install instructions |
| engine.py | Invalid FEN | `ValueError` with message |
| engine.py | Stockfish crash | Catch, attempt one restart |
| srs.py | Corrupted JSON | Backup corrupted file, start fresh |
| srs.py | Card not found | `ValueError` with card ID |
| MCP server | Invalid game_id | Return error dict |
| MCP server | Illegal move | Return error dict with legal moves |
| MCP server | Game over | Return error dict with result |
| TUI | Missing JSON | Show "Waiting for game..." |
| TUI | Corrupt JSON | Show last valid state |
| export.py | Missing data | Friendly "no data" message |
| install.sh | Stockfish install fails | Print manual instructions |
| puzzles | Invalid FEN | validate_puzzles.py catches and reports |

## Decisions Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Split US-004 into 3 stories | 12 MCP tools too large for one ralph iteration |
| 2 | Reorder refs + puzzles before SKILL.md | SKILL.md references these files, they should exist first |
| 3 | Renumber stories US-001 to US-013 | Clean sequential numbering for ralph loop |
| 4 | Tests for core only (engine, SRS) | Other stories validated by syntax + import + CLI smoke |
| 5 | File exists + sections for doc validation | Rigorous enough without being fragile |
| 6 | Single server.py for all MCP tools | Simpler than modular, tools just append to same file |
| 7 | TUI standalone with sample JSON | No MCP dependency for testing TUI rendering |
| 8 | Engine CLI: demo + --interactive flag | One-move demo for testing, interactive for actual use |
| 9 | uv for environment management | Modern, fast, handles venv + deps in one tool |
| 10 | Every-move JSON sync | TUI needs fresh state, atomic writes prevent corruption |
| 11 | Tactical motif = None for now | Motif detection complex, defer to future enhancement |
| 12 | ISO 8601 timestamps | Human-readable in JSON files |
| 13 | Linear scale for sub-1320 Elo | Simple, predictable difficulty progression |
| 14 | Markdown export format | Human-readable, Claude can reference in conversations |
| 15 | models.py created in US-001 | Shared dataclasses needed by MCP and TUI, avoids circular deps |
| 16 | Programmatic FEN validation | LLM-generated FENs are often invalid, must verify |
| 17 | GameState as shared dataclass | Single source of truth for MCP <-> TUI contract |
