# Chess Rocket

An adaptive chess tutoring system powered by Claude Code that transforms you into a personalized chess coach. Combines Stockfish engine analysis with educational psychology to guide learners from beginner (0 Elo) to intermediate (1500 Elo) through structured play, analysis, and spaced repetition.

**Status:** Python 3.10+ | Stockfish Engine | FastMCP | SQLite | Rich TUI

---

## Overview

Chess Rocket works as a complete learning ecosystem:

1. **Claude Code** connects via MCP (Model Context Protocol) to a chess server
2. **MCP Server** manages 17+ tools for games, analysis, openings, and progress tracking
3. **Stockfish** engine provides position evaluation and engine play
4. **Rich TUI** displays the live board, moves, evaluation, and opening info in a separate terminal
5. **Spaced Repetition (SM-2)** automatically schedules mistake review for long-term retention

The system implements a **3-perspective tutor**: GM Teacher (strategy), Learning Psychologist (pacing), and Behavioral Specialist (motivation).

---

## Architecture

```
Claude Code (Tutor Agent)
        │
        ├──MCP Protocol──► MCP Server (FastMCP)
        │                    │
        │                    ├── GameEngine (Stockfish wrapper)
        │                    ├── OpeningsDB (3,627 openings)
        │                    ├── SRSManager (SM-2 spaced rep)
        │                    └── Tools (17+ tools)
        │                    │
        │                    └─► data/current_game.json (atomic writes)
        │
        └── Terminal 2: TUI (Rich/Textual, 4Hz poll)
             Display: Board | Moves | Eval | Opening | Accuracy
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| Chess Engine | Stockfish (UCI protocol) |
| MCP Framework | FastMCP |
| TUI | Rich + Textual |
| Database | SQLite (openings) + JSON (game state) |
| Package Manager | uv |
| Testing | pytest |
| File Watching | watchdog |

---

## Features

### Game Management (17+ MCP Tools)
- Full game lifecycle: `new_game`, `make_move`, `engine_move`, `undo_move`
- Deep analysis: `analyze_position`, `evaluate_move`
- Difficulty control: `set_difficulty` (100-3500 Elo)
- Legal moves, PGN export, board state tracking

### Adaptive Difficulty
- **100-1320 Elo:** Custom linear blend formula with depth-limited Stockfish + random moves
- **1320-3500 Elo:** Direct Stockfish UCI_Elo control
- **Auto-adjustment:** Difficulty scales ±50-100 Elo based on recent accuracy

### Opening Recognition & Study
- **3,627 chess openings** from Lichess database
- Live identification during games (ECO code + name)
- Search by name or ECO code
- Level-appropriate opening suggestions
- Interactive opening quizzes
- Opening trap refutation puzzles

### Spaced Repetition (SM-2 Algorithm)
- Automatic mistake card creation
- Review intervals: 4hr → 1d → 3d → 1wk → 2wk → 1mo
- Quality-based progression (0-5 scale)
- Failed reviews reset to 4hr
- Ease factor adjustment per card

### Curated Learning Content
- **7 Educational References**: Curriculum, pedagogy, learning science, Elo milestones, tactical patterns, common mistakes, opening guide
- **132 Tactical Puzzles** across 8 themes:
  - Forks (12), Pins (12), Skewers (11)
  - Back-rank threats (12), Checkmate patterns (11)
  - Basic endgames (11), Opening moves (35)
  - Opening traps (22)
- **3-Phase Curriculum**: Foundation (0-600) → Tactical (600-1000) → Intermediate (1000-1500)

### Live Terminal UI
- Unicode chess board display
- Move list with move numbers
- Evaluation bar (position assessment)
- Current opening name + ECO code
- Game accuracy tracker
- Real-time board updates (4Hz polling)
- Sample mode for testing without live game

### Post-Game Analysis
- Batch SRS card creation for all mistakes (>80cp loss)
- Teaching position selection
- Accuracy summary + move classification
- Session logging and progress updates
- PGN auto-save

---

## Project Structure

```
chess_rocket/
├── mcp-server/
│   ├── server.py              # 17+ MCP tools (game, analysis, openings, utility)
│   └── openings_tools.py      # Opening recognition (5 tools)
├── scripts/
│   ├── engine.py              # Stockfish wrapper with adaptive difficulty
│   ├── srs.py                 # SM-2 spaced repetition system
│   ├── tui.py                 # Rich-based terminal UI (board display)
│   ├── openings.py            # Opening recognition (trie + SQLite lookup)
│   ├── models.py              # Shared data models (GameState, MoveEvaluation)
│   ├── export.py              # Progress/game markdown reports
│   ├── install.sh             # Setup script
│   ├── build_openings_db.py   # Download & build 3,627 openings
│   ├── generate_opening_puzzles.py
│   └── validate_puzzles.py    # FEN validation
├── references/                # Educational content (7 files)
│   ├── curriculum.md          # 3-phase curriculum framework
│   ├── chess-pedagogy.md      # GM coaching methodology
│   ├── learning-science.md    # Cognitive science foundations
│   ├── elo-milestones.md      # Skills expected by Elo range
│   ├── tactical-patterns.md   # Tactical motifs with examples
│   ├── common-mistakes.md     # Beginner error patterns
│   └── opening-guide.md       # Level-appropriate openings
├── puzzles/                   # 132 curated puzzles (8 files)
│   ├── forks.json (12 puzzles)
│   ├── pins.json (12)
│   ├── skewers.json (11)
│   ├── back-rank.json (12)
│   ├── checkmate-patterns.json (11)
│   ├── beginner-endgames.json (11)
│   ├── opening-moves.json (35)
│   └── opening-traps.json (22)
├── tests/
│   ├── test_engine.py         # Stockfish wrapper tests
│   ├── test_srs.py            # SM-2 algorithm tests
│   ├── test_openings.py       # Opening recognition tests
│   └── test_post_game.py      # Post-game analysis tests
├── data/                      # Runtime data (generated, gitignored)
│   ├── current_game.json      # Live game state (MCP ↔ TUI sync)
│   ├── progress.json          # Player Elo, sessions, streak
│   ├── srs_cards.json         # SRS review card history
│   ├── openings.db            # SQLite: 3,627 openings
│   ├── openings_trie.json     # JSON trie for fast ECO lookup
│   ├── sessions/              # Session logs (JSON)
│   ├── games/                 # Saved PGN files
│   └── lesson_plans/          # Generated lesson plans
├── CLAUDE.md                  # Tutor agent instructions
├── SKILL.md                   # Claude Code skill documentation
├── pyproject.toml             # Python project config (uv)
├── .mcp.json                  # MCP server config
└── README.md                  # This file
```

---

## Getting Started

### Prerequisites
- Python 3.10 or later
- Stockfish chess engine
- uv package manager
- Claude Code (with MCP support)

### Installation

```bash
git clone https://github.com/suvojit-0x55aa/chess_rocket.git
cd chess_rocket
./scripts/install.sh
```

The install script:
1. Installs Stockfish (via Homebrew on macOS, apt on Linux)
2. Installs uv package manager
3. Creates Python virtual environment
4. Initializes `data/` directories and `progress.json`
5. Downloads and builds the 3,627-opening database
6. Validates all puzzle FENs

### Quick Start

**Terminal 1 — Start the TUI:**
```bash
uv run python scripts/tui.py
```

**Terminal 2 — Start Claude Code & Connect:**
```bash
# Claude connects to the MCP server automatically
# Say: "Let's play chess" or "Start a game"
```

The board appears in Terminal 1, updates in real-time as you play.

---

## Usage

### Interactive Play

Claude manages the full session:
1. Evaluates your moves before responding
2. Teaches based on move quality (see thresholds below)
3. Tracks opening name during play
4. Offers undo on blunders
5. Analyzes game after completion
6. Creates SRS cards for mistakes

### Standalone Commands

```bash
# View live board with sample game data
uv run python scripts/tui.py --sample

# Engine analysis of a position
uv run python scripts/engine.py analyze "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# Engine play (one move only)
uv run python scripts/engine.py play 800

# Engine play (interactive game loop)
uv run python scripts/engine.py play 800 --interactive

# View due SRS review cards
uv run python scripts/srs.py due

# Export progress report (markdown)
uv run python scripts/export.py progress

# Export game PGN summaries
uv run python scripts/export.py games

# Run full test suite
uv run python -m pytest tests/ -v
```

---

## How It Works

### Teaching Methodology

Claude acts as a **3-perspective tutor**:

| Role | Function |
|------|----------|
| **GM Teacher** | Position evaluation, pattern recognition, opening principles |
| **Learning Psychologist** | Zone of Proximal Development, spaced rep scheduling, deliberate practice |
| **Behavioral Specialist** | Session pacing, streak tracking, difficulty calibration |

### Core Loop: Play → Analyze → Teach → Replay → Plan

1. **Play**: You move. Claude evaluates with `evaluate_move()` before responding with engine move.
2. **Analyze**: Claude compares your choice to engine's top moves using `analyze_position()`.
3. **Teach**: Response depth depends on move quality (see thresholds below).
4. **Replay**: After game, Claude walks through 2-3 teaching positions.
5. **Plan**: Session summary + lesson plan + next session goals.

### Move Evaluation Thresholds

| CP Loss | Classification | Teaching Response |
|---------|---------------|-------------------|
| 0 | Best move | Brief acknowledgment ("Excellent!") |
| 1-30 | Great move | Positive reinforcement |
| 31-80 | Good move | Note the slightly better alternative |
| 81-150 | Inaccuracy | Brief teaching: why alternative is better |
| 151-300 | Mistake | Full explanation + principle connection |
| 300+ | Blunder | Immediate intervention + undo offer + add to SRS |

### Language Adaptation

Claude adjusts explanation depth to your level:

| Level | Elo Range | Approach |
|-------|-----------|----------|
| **Beginner** | 0-600 | Simple terms, visual explanations, piece safety focus |
| **Intermediate Beginner** | 600-1000 | Terminology intro, principle-based, tactical patterns |
| **Intermediate** | 1000-1500 | Full technical language, positional play, strategy |

---

## MCP Tools Reference

### Game Management (8 tools)
`new_game` • `get_board` • `make_move` • `engine_move` • `undo_move` • `set_position` • `get_legal_moves` • `get_game_pgn`

### Analysis (3 tools)
`analyze_position` • `evaluate_move` • `set_difficulty`

### Openings (5 tools)
`identify_opening` • `search_openings` • `get_opening_details` • `suggest_opening` • `opening_quiz`

### Progress & Learning (2+ tools)
`srs_add_card` • `create_srs_cards_from_game` • `save_session`

---

## Data Files & Formats

| File | Purpose |
|------|---------|
| `data/progress.json` | Player Elo estimate, session count, win/loss/draw stats, streak |
| `data/srs_cards.json` | SRS review history (timestamps, intervals, ease factors) |
| `data/current_game.json` | Live game state synced between MCP server and TUI |
| `data/openings.db` | SQLite: ECO codes, move sequences, opening names (3,627 total) |
| `data/openings_trie.json` | JSON trie for fast ECO code lookup during games |
| `data/sessions/*.json` | Session logs (moves, accuracy, lesson focus, improvements) |
| `data/games/*.pgn` | Saved games in PGN format |

All data is JSON or SQLite for easy inspection and backup.

---

## Adaptive Difficulty

The engine automatically adjusts to match your skill:

```
If recent accuracy > 90%:
  → Increase difficulty by 100 Elo (too easy)
If recent accuracy 80-90%:
  → Increase by 50 Elo (performing well)
If recent accuracy 65-80%:
  → Keep same difficulty (zone of proximal development)
If recent accuracy 50-65%:
  → Decrease by 50 Elo (struggling)
If recent accuracy < 50%:
  → Decrease by 100 Elo (too hard)
```

Sub-1320 Elo uses a custom formula: random move injection + depth limiting (Stockfish's minimum UCI_Elo is 1320).

---

## Opening System

**3,627 openings** from the Lichess database:

- **Live identification**: Opening name displayed during games as you follow book moves
- **ECO search**: Find openings by name or ECO code (B20, E4, etc.)
- **Suggestions**: Get level-appropriate openings to study based on your Elo
- **Quizzes**: Test your opening knowledge with "what's the next move?" challenges
- **Traps**: Learn common opening traps and their refutations

Openings stored in SQLite + JSON trie for fast lookup.

---

## Spaced Repetition (SM-2)

Powered by the **SM-2 algorithm** (industry standard):

- **First review**: 4 hours after mistake
- **Successful reviews advance**: 4hr → 1d → 3d → 1wk → 2wk → 1mo
- **Failed reviews reset**: Back to 4hr if quality < 3
- **Quality scale**: 0-2 (failed), 3-5 (passed)
- **Ease factor**: Adjusted per card based on quality history

Claude automatically creates SRS cards for:
- Significant mistakes during games (>80cp loss)
- Manually marked positions
- Opening knowledge gaps

---

## Testing

Comprehensive test coverage:

```bash
# Run all tests
uv run python -m pytest tests/ -v

# Test specific module
uv run python -m pytest tests/test_engine.py -v

# Test coverage report
uv run python -m pytest tests/ --cov=scripts --cov-report=html
```

**Test suites:**
- `test_engine.py` — Stockfish wrapper, adaptive difficulty
- `test_srs.py` — SM-2 algorithm, card scheduling
- `test_openings.py` — Opening identification, search, ECO lookup
- `test_post_game.py` — Game analysis, SRS card creation

---

## Development

### Architecture Decisions

- **Shared Models**: `scripts/models.py` defines `GameState` and `MoveEvaluation` dataclasses used by MCP server and TUI
- **Atomic Writes**: All JSON updates use temp file + `os.replace()` to prevent corruption
- **4Hz TUI Polling**: Current game state read from `data/current_game.json` every 250ms
- **Programmatic FEN Validation**: All puzzle FENs validated via `python-chess` before save
- **Sub-1320 Elo**: Linear blend formula for random move injection (Stockfish minimum is 1320)

### Adding New Features

1. **New MCP Tool**: Add to `mcp-server/server.py` with `@server.call_tool()` decorator
2. **New Puzzle Set**: Add JSON file to `puzzles/` with format: `[{"fen": "...", "solution": [...], "theme": "..."}]`
3. **New Reference**: Add markdown file to `references/` and link from `CLAUDE.md`
4. **Opening Support**: Pre-built 3,627 openings; search/quiz/suggest all work automatically

---

## References

- **CLAUDE.md** — Full tutor agent instructions (session flow, teaching methodology, tool reference)
- **SKILL.md** — Claude Code skill documentation (for other agents)
- **chess-speedrun-prd.md** — Product requirements document
- **references/** — 7 educational materials for the tutor to reference

---

## License

This is a personal project. Add appropriate license (MIT, Apache, etc.) as needed.

---

## Contributing

Contributions welcome! Areas of interest:
- Additional puzzle sets or tactical themes
- New reference materials or teaching techniques
- Performance optimizations for opening lookups
- TUI enhancements
- Language localization

---

## Support

For issues or questions:
1. Check `CLAUDE.md` for tutor instructions
2. Review `references/` for teaching methodology
3. Run `./scripts/install.sh` to verify setup
4. Run test suite: `uv run python -m pytest tests/ -v`

Enjoy learning chess with your personal tutor!
