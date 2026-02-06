# Chess Speedrun - Ralph Agent Instructions

You are an autonomous coding agent building a Chess Speedrun Learning System.

## Project Overview

This project transforms Claude Code into an adaptive chess tutor. Stockfish handles analysis via an MCP server. A Rich-based TUI handles board display. Claude Code handles all teaching intelligence.

Key components:
- `scripts/install.sh` - Setup script (Stockfish + uv env + Python deps)
- `scripts/models.py` - Shared dataclasses (GameState, MoveEvaluation) used by MCP + TUI
- `scripts/engine.py` - Stockfish UCI wrapper with adaptive difficulty (sub-1320 uses linear blend)
- `scripts/srs.py` - SM-2 spaced repetition card manager
- `scripts/tui.py` - Terminal chess board UI (Rich, watches current_game.json at 4Hz)
- `scripts/export.py` - Progress/game export as markdown
- `scripts/validate_puzzles.py` - Programmatic FEN validation for puzzle files
- `mcp-server/server.py` - MCP server exposing 13 Stockfish tools (built in 3 stories: core/analysis/utility)
- `SKILL.md` - Main skill file for the chess tutor
- `references/` - Curriculum, pedagogy, patterns, mistakes, openings documentation
- `puzzles/` - Curated puzzle positions by motif (6 JSON files, 10+ each)
- `data/` - User progress, sessions, games, SRS cards
- `documentation/` - Canonical PRD documentation with all decisions

## Your Task

1. Read the PRD at `prd.json`
2. Read the progress log at `progress.txt` (check Codebase Patterns section first)
3. Check you're on the correct branch from PRD `branchName`. If not, check it out or create from main.
4. Pick the **highest priority** user story where `passes: false`
5. Implement that single user story
6. Run quality checks (python syntax check, typecheck if applicable, test if available)
7. Update CLAUDE.md if you discover reusable patterns
8. If checks pass, commit ALL changes with message: `feat: [Story ID] - [Story Title]`
9. Update the PRD to set `passes: true` for the completed story
10. Append your progress to `progress.txt`

## Progress Report Format

APPEND to progress.txt (never replace, always append):
```
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- **Learnings for future iterations:**
  - Patterns discovered (e.g., "this codebase uses X for Y")
  - Gotchas encountered (e.g., "don't forget to update Z when changing W")
  - Useful context (e.g., "the MCP server expects JSON responses")
---
```

The learnings section is critical - it helps future iterations avoid repeating mistakes and understand the codebase better.

## Consolidate Patterns

If you discover a **reusable pattern** that future iterations should know, add it to the `## Codebase Patterns` section at the TOP of progress.txt (create it if it doesn't exist). This section should consolidate the most important learnings:

```
## Codebase Patterns
- python-chess Board objects are mutable - always copy before analysis
- Stockfish UCI_Elo minimum is 1320, use depth limiting + random moves below that
- MCP server uses FastMCP from mcp.server.fastmcp
- TUI syncs via data/current_game.json file polling at 4Hz
- SRS uses SM-2 algorithm with intervals: 4hr → 1d → 3d → 1wk → 2wk → 1mo
- All data files go in data/ directory
- Progress state in data/progress.json
```

Only add patterns that are **general and reusable**, not story-specific details.

## Quality Requirements

- ALL commits must pass quality checks
- Run `python -m py_compile <file>` to verify Python syntax
- Run `python -c "from scripts.<module> import <Class>"` to verify imports resolve
- Run `python -m pytest tests/` if test files exist (US-002 and US-003 have pytest tests)
- Run `python scripts/validate_puzzles.py` after US-010 to verify FENs
- Do NOT commit broken code
- Keep changes focused and minimal
- Follow existing code patterns

## Canonical Documentation

Full design decisions and specifications are in `documentation/general_chess_speedrun_prd_documentation.md`.
Read this file when you need detailed specifications for a story (data schemas, error handling, edge cases).

## Story Dependency Order (13 stories)

```
US-001: Install + project structure + models.py
US-002: Engine wrapper + pytest tests
US-003: SRS manager + pytest tests
US-004: MCP server - core game tools (new_game, get_board, make_move, engine_move)
US-005: MCP server - analysis tools (analyze_position, evaluate_move, set_difficulty)
US-006: MCP server - utility tools (pgn, legal_moves, undo, set_position, srs_add_card)
US-007: TUI with Rich (standalone with sample JSON)
US-008: Reference docs - curriculum & pedagogy
US-009: Reference docs - tactics & mistakes
US-010: Puzzle sets + FEN validation script
US-011: SKILL.md (references actual files from US-008/009/010)
US-012: Export script (markdown output)
US-013: Claude settings + integration verification
```

## Tech Stack

- Python 3.10+
- uv (environment management - NOT pip/venv)
- python-chess (chess library)
- Stockfish (chess engine, installed via brew/apt)
- Rich / Textual (terminal UI)
- watchdog (file system watcher for TUI)
- MCP SDK (mcp[cli] package) for MCP server using FastMCP
- JSON files for data persistence (ISO 8601 timestamps)

## Stop Condition

After completing a user story, check if ALL stories have `passes: true`.

If ALL stories are complete and passing, reply with:
<promise>COMPLETE</promise>

If there are still stories with `passes: false`, end your response normally (another iteration will pick up the next story).

## Important

- Work on ONE story per iteration
- Commit frequently
- Keep CI green
- Read the Codebase Patterns section in progress.txt before starting
- Each iteration is a fresh context - memory persists only via git, progress.txt, and prd.json
