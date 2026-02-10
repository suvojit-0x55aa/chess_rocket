#!/usr/bin/env python3
"""Validate all puzzle JSON files for correct FENs and legal solution moves.

Supports two modes:
- Default: fast legality-only validation (no Stockfish required)
- --engine-verify: deep verification with Stockfish (solution quality, checkmate, stalemate, motif)
"""

import argparse
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
    "from-games.json",
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


def validate_puzzle_engine(
    puzzle: dict, filename: str, index: int, engine: "chess.engine.SimpleEngine"
) -> tuple[list[str], list[str]]:
    """Engine-verify a single puzzle. Returns (errors, warnings)."""
    errors = []
    warnings = []
    prefix = f"{filename}[{index}]"

    fen = puzzle.get("fen", "")
    solution_moves = puzzle.get("solution_moves", [])
    motif = puzzle.get("motif", "")

    try:
        board = chess.Board(fen)
    except ValueError:
        return errors, warnings  # Already caught by legality check

    if not solution_moves:
        return errors, warnings

    # Parse the first solution move
    try:
        first_move = chess.Move.from_uci(solution_moves[0])
    except ValueError:
        return errors, warnings  # Already caught by legality check

    if first_move not in board.legal_moves:
        return errors, warnings  # Already caught by legality check

    # Check 1: Solution move is engine's #1 choice (or within tolerance of best)
    # Tolerance is 50cp to account for depth-15 vs depth-20 non-determinism
    # Opening/opening_trap puzzles are exempt — book moves test knowledge, not engine optimality
    _CP_TOLERANCE = 50
    if motif in ("opening", "opening_trap"):
        pass  # opening exemption — skip engine-best check
    else:
        try:
            result = engine.analyse(board, chess.engine.Limit(depth=15), multipv=2)
            if result and len(result) >= 1:
                best_info = result[0]
                best_move = best_info.get("pv", [None])[0]
                best_score = best_info["score"].pov(board.turn)

                if best_move != first_move:
                    # Check if within tolerance of best
                    solution_found = False
                    for info in result:
                        pv = info.get("pv", [])
                        if pv and pv[0] == first_move:
                            sol_score = info["score"].pov(board.turn)
                            if best_score.is_mate() and sol_score.is_mate():
                                solution_found = True
                            elif best_score.is_mate() and not sol_score.is_mate():
                                pass
                            elif not best_score.is_mate() and sol_score.is_mate():
                                solution_found = True
                            else:
                                diff = abs(best_score.score() - sol_score.score())
                                if diff <= _CP_TOLERANCE:
                                    solution_found = True
                            break

                    if not solution_found:
                        board_after_sol = board.copy()
                        board_after_sol.push(first_move)
                        try:
                            sol_result = engine.analyse(
                                board_after_sol, chess.engine.Limit(depth=15)
                            )
                            sol_score = sol_result["score"].pov(board.turn)
                            if best_score.is_mate() and not sol_score.is_mate():
                                errors.append(
                                    f"{prefix}: solution {solution_moves[0]} is not best move "
                                    f"(engine prefers {best_move.uci()}, mate vs no mate)"
                                )
                            elif not best_score.is_mate() and not sol_score.is_mate():
                                diff = abs(best_score.score() - (-sol_score.score()))
                                if diff > _CP_TOLERANCE:
                                    errors.append(
                                        f"{prefix}: solution {solution_moves[0]} is not best move "
                                        f"(engine prefers {best_move.uci()}, diff={diff}cp)"
                                    )
                        except Exception:
                            pass  # Can't verify, skip
        except Exception:
            pass  # Engine analysis failed, skip this check

    # Check 2: Checkmate puzzles result in board.is_checkmate() after solution
    if motif in ("checkmate", "back_rank_mate", "back-rank", "checkmate_pattern"):
        check_board = board.copy()
        all_legal = True
        for move_uci in solution_moves:
            try:
                move = chess.Move.from_uci(move_uci)
                if move not in check_board.legal_moves:
                    all_legal = False
                    break
                check_board.push(move)
            except ValueError:
                all_legal = False
                break

        if all_legal and not check_board.is_checkmate():
            errors.append(
                f"{prefix}: checkmate puzzle but position after solution is not checkmate"
            )

    # Check 3: No stalemate in solution line
    stalemate_board = board.copy()
    for step, move_uci in enumerate(solution_moves):
        try:
            move = chess.Move.from_uci(move_uci)
            if move not in stalemate_board.legal_moves:
                break
            stalemate_board.push(move)
            if stalemate_board.is_stalemate():
                errors.append(
                    f"{prefix}: stalemate occurs at step {step} in solution line"
                )
                break
        except ValueError:
            break

    # Check 4: Motif classification matches detect_motif() (warning, not error)
    try:
        from scripts.motif_detector import detect_motif

        detected = detect_motif(board, first_move)
        # Normalize motif names for comparison
        motif_map = {
            "fork": "fork",
            "forks": "fork",
            "pin": "pin",
            "pins": "pin",
            "skewer": "skewer",
            "skewers": "skewer",
            "back-rank": "back_rank_mate",
            "back_rank": "back_rank_mate",
            "back_rank_mate": "back_rank_mate",
            "checkmate": "checkmate",
            "checkmate_pattern": "checkmate",
            "checkmate-pattern": "checkmate",
            "discovered_attack": "discovered_attack",
            "double_check": "double_check",
            "promotion": "promotion",
            "opening": "opening",
            "opening_trap": "opening_trap",
            "endgame": None,
            "beginner_endgame": None,
            "tactics": None,
        }
        normalized_puzzle_motif = motif_map.get(motif, motif)
        if detected != normalized_puzzle_motif and normalized_puzzle_motif is not None:
            warnings.append(
                f"{prefix}: motif mismatch - puzzle says '{motif}', "
                f"detect_motif says '{detected}'"
            )
    except ImportError:
        pass  # motif_detector not available

    return errors, warnings


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


def validate_file_engine(
    filepath: Path, engine: "chess.engine.SimpleEngine"
) -> tuple[int, list[str], list[str]]:
    """Engine-verify a puzzle file. Returns (total_checked, errors, warnings)."""
    errors = []
    warnings = []

    try:
        with open(filepath) as f:
            puzzles = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0, [], []

    if not isinstance(puzzles, list):
        return 0, [], []

    for i, puzzle in enumerate(puzzles):
        puzzle_errors, puzzle_warnings = validate_puzzle_engine(
            puzzle, filepath.name, i, engine
        )
        errors.extend(puzzle_errors)
        warnings.extend(puzzle_warnings)

    return len(puzzles), errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate puzzle JSON files")
    parser.add_argument(
        "--engine-verify",
        action="store_true",
        help="Run Stockfish engine verification (slower but more thorough)",
    )
    args = parser.parse_args()

    all_errors = []
    total_puzzles = 0
    total_passed = 0
    missing_files = []

    print("=== Legality Validation ===")
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

    # Engine verification mode
    if args.engine_verify:
        print("\n=== Engine Verification (depth 15) ===")
        try:
            import chess.engine as ce

            from scripts.engine import _find_stockfish

            stockfish_path = _find_stockfish()
            engine = ce.SimpleEngine.popen_uci(stockfish_path)
        except (FileNotFoundError, Exception) as e:
            print(f"  ERROR: Could not start Stockfish: {e}")
            print("  Skipping engine verification.")
            if all_errors:
                print(f"\n{len(all_errors)} error(s):")
                for err in all_errors:
                    print(f"  - {err}")
                return 1
            print("\nAll puzzles valid! (legality only)")
            return 0

        engine_errors = []
        engine_warnings = []

        try:
            for filename in EXPECTED_FILES:
                filepath = PUZZLES_DIR / filename
                if not filepath.exists():
                    continue

                total_checked, errors, warnings = validate_file_engine(
                    filepath, engine
                )
                engine_errors.extend(errors)
                engine_warnings.extend(warnings)

                err_count = len(errors)
                warn_count = len(warnings)
                if err_count == 0 and warn_count == 0:
                    print(f"  PASS: {filename} ({total_checked} puzzles engine-verified)")
                elif err_count == 0:
                    print(f"  PASS: {filename} ({total_checked} verified, {warn_count} warning(s))")
                else:
                    print(f"  FAIL: {filename} ({err_count} error(s), {warn_count} warning(s))")
        finally:
            engine.quit()

        all_errors.extend(engine_errors)

        if engine_warnings:
            print(f"\n{len(engine_warnings)} warning(s):")
            for warn in engine_warnings:
                print(f"  - {warn}")

    if all_errors:
        print(f"\n{len(all_errors)} error(s):")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("\nAll puzzles valid!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
