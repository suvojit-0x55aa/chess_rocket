# Chess Speedrun - Ralph Agent Instructions

You are an autonomous coding agent building a Chess Speedrun Learning System.

## Project Overview

This project transforms Claude Code into an adaptive chess tutor. Stockfish handles analysis via an MCP server. A Rich-based TUI handles board display. Claude Code handles all teaching intelligence.

Key components:
- `scripts/engine.py` - Stockfish UCI wrapper with difficulty control
- `scripts/tui.py` - Terminal chess board UI (Rich/Textual)
- `scripts/srs.py` - Spaced repetition card manager
- `scripts/install.sh` - Setup script for Stockfish + Python deps
- `mcp-server/server.py` - MCP server exposing Stockfish as tools
- `SKILL.md` - Main skill file for the chess tutor
- `references/` - Curriculum, pedagogy, patterns documentation
- `puzzles/` - Curated puzzle positions by motif
- `data/` - User progress, sessions, games, SRS cards

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
- Run tests if available: `python -m pytest` (if tests exist)
- Do NOT commit broken code
- Keep changes focused and minimal
- Follow existing code patterns

## Tech Stack

- Python 3.10+
- python-chess (chess library)
- Stockfish (chess engine, installed via brew/apt)
- Rich / Textual (terminal UI)
- MCP SDK (mcp package) for MCP server
- JSON files for data persistence

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
