#!/usr/bin/env python3
"""Validate all puzzle JSON files for correct FENs and legal solution moves."""

import json
import sys
from pathlib import Path

import chess

PUZZLES_DIR = Path(__file__).parent.parent / "puzzles"

EXPECTED_FILES = [
    "forks.json",
    "pins.json",
    "skewers.json",
    "back-rank.json",
    "checkmate-patterns.json",
    "beginner-endgames.json",
    "opening-moves.json",
    "opening-traps.json",
]

REQUIRED_FIELDS = ["fen", "solution_moves", "solution_san", "motif", "difficulty", "explanation"]


def validate_puzzle(puzzle: dict, filename: str, index: int) -> list[str]:
    """Validate a single puzzle. Returns list of error messages."""
    errors = []
    prefix = f"{filename}[{index}]"

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in puzzle:
            errors.append(f"{prefix}: missing field '{field}'")

    if errors:
        return errors

    fen = puzzle["fen"]
    solution_moves = puzzle["solution_moves"]

    # Validate FEN
    try:
        board = chess.Board(fen)
    except ValueError as e:
        errors.append(f"{prefix}: invalid FEN '{fen}': {e}")
        return errors

    # Validate solution moves are legal in sequence
    for i, move_uci in enumerate(solution_moves):
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            errors.append(f"{prefix}: invalid UCI move '{move_uci}' at step {i}")
            break

        if move not in board.legal_moves:
            errors.append(
                f"{prefix}: illegal move '{move_uci}' at step {i} "
                f"(FEN: {board.fen()})"
            )
            break

        board.push(move)

    return errors


def validate_file(filepath: Path) -> tuple[int, int, list[str]]:
    """Validate a puzzle file. Returns (total, passed, errors)."""
    errors = []

    try:
        with open(filepath) as f:
            puzzles = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return 0, 0, [f"{filepath.name}: failed to load: {e}"]

    if not isinstance(puzzles, list):
        return 0, 0, [f"{filepath.name}: expected a JSON array"]

    total = len(puzzles)
    passed = 0

    for i, puzzle in enumerate(puzzles):
        puzzle_errors = validate_puzzle(puzzle, filepath.name, i)
        if puzzle_errors:
            errors.extend(puzzle_errors)
        else:
            passed += 1

    return total, passed, errors


def main() -> int:
    all_errors = []
    total_puzzles = 0
    total_passed = 0
    missing_files = []

    for filename in EXPECTED_FILES:
        filepath = PUZZLES_DIR / filename
        if not filepath.exists():
            missing_files.append(filename)
            continue

        total, passed, errors = validate_file(filepath)
        total_puzzles += total
        total_passed += passed
        all_errors.extend(errors)

        status = "PASS" if not errors and total >= 10 else "FAIL"
        count_info = f"({passed}/{total} puzzles valid)"
        if total < 10:
            count_info += " - needs 10+ puzzles"
            if not errors:
                all_errors.append(f"{filename}: only {total} puzzles (need 10+)")
        print(f"  {status}: {filename} {count_info}")

    if missing_files:
        for f in missing_files:
            print(f"  FAIL: {f} (file not found)")
            all_errors.append(f"{f}: file not found")

    print(f"\nTotal: {total_passed}/{total_puzzles} puzzles valid across {len(EXPECTED_FILES)} files")

    if all_errors:
        print(f"\n{len(all_errors)} error(s):")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("\nAll puzzles valid!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
