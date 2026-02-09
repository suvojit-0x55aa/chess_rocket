#!/usr/bin/env python3
"""Import puzzles from the Lichess puzzle database (CSV.ZST format).

Streams data/lichess_db_puzzle.csv.zst, filters by theme/rating/popularity,
converts to chess_rocket puzzle format with full validation.

Lichess CSV columns:
  PuzzleId, FEN, Moves, Rating, RatingDeviation, Popularity, NbPlays,
  Themes, GameUrl, OpeningTags

Key format detail: Lichess FEN is the game position BEFORE the puzzle setup
move. moves[0] is applied to reach the puzzle position, then moves[1:] are
the solution (alternating: player solution move, opponent forced response).
"""

import argparse
import csv
import io
import json
import sys
from pathlib import Path

import chess
import zstandard

# Theme-to-motif mapping
THEME_TO_MOTIF: dict[str, str] = {
    "backRankMate": "back_rank_mate",
    "mateIn1": "checkmate",
    "mateIn2": "checkmate",
    "mateIn3": "checkmate",
    "smotheredMate": "checkmate",
    "arabianMate": "checkmate",
    "anastasiasMate": "checkmate",
    "fork": "fork",
    "pin": "pin",
    "skewer": "skewer",
    "discoveredAttack": "discovered_attack",
    "doubleCheck": "double_check",
    "promotion": "promotion",
}

# Motif-specific explanation templates
EXPLANATION_TEMPLATES: dict[str, str] = {
    "back_rank_mate": "Find the back-rank mate! The king is trapped by its own pieces.",
    "checkmate": "Find the checkmate! Look for forcing moves that leave no escape.",
    "fork": "Find the fork! Attack two or more pieces simultaneously.",
    "pin": "Exploit the pin! The pinned piece cannot move without exposing a more valuable piece.",
    "skewer": "Find the skewer! Attack a valuable piece that must move, exposing a piece behind it.",
    "discovered_attack": "Find the discovered attack! Moving one piece reveals an attack from another.",
    "double_check": "Find the double check! Two pieces give check simultaneously.",
    "promotion": "Find the promotion! Push the pawn to the last rank.",
}

DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_DB = DATA_DIR / "lichess_db_puzzle.csv.zst"


def _rating_to_difficulty(rating: int) -> str:
    """Map Lichess puzzle rating to difficulty label."""
    if rating < 1200:
        return "beginner"
    if rating < 1800:
        return "intermediate"
    return "advanced"


def _normalize_fen(fen: str) -> str:
    """Strip move counters from FEN for deduplication."""
    parts = fen.split()
    return " ".join(parts[:4]) if len(parts) >= 4 else fen


def _pick_motif(themes: list[str]) -> str | None:
    """Pick the best motif from a list of Lichess themes."""
    for theme in themes:
        if theme in THEME_TO_MOTIF:
            return THEME_TO_MOTIF[theme]
    return None


def _moves_to_san(board: chess.Board, uci_moves: list[str]) -> list[str]:
    """Convert a sequence of UCI moves to SAN, advancing the board."""
    san_list = []
    for uci in uci_moves:
        move = chess.Move.from_uci(uci)
        san_list.append(board.san(move))
        board.push(move)
    return san_list


def _validate_checkmate(board: chess.Board, solution_uci: list[str]) -> bool:
    """Verify that applying solution moves results in checkmate."""
    b = board.copy()
    for uci in solution_uci:
        move = chess.Move.from_uci(uci)
        if move not in b.legal_moves:
            return False
        b.push(move)
    return b.is_checkmate()


def _validate_back_rank(board: chess.Board, solution_uci: list[str]) -> bool:
    """Verify checkmate occurs and king is on rank 1 or 8."""
    b = board.copy()
    for uci in solution_uci:
        move = chess.Move.from_uci(uci)
        if move not in b.legal_moves:
            return False
        b.push(move)
    if not b.is_checkmate():
        return False
    # Find the mated king
    loser = b.turn  # side to move is the one in checkmate
    king_sq = b.king(loser)
    if king_sq is None:
        return False
    rank = chess.square_rank(king_sq)
    return rank == 0 or rank == 7


def import_puzzles(
    db_path: Path,
    themes: list[str],
    min_rating: int = 0,
    max_rating: int = 9999,
    min_popularity: int = 80,
    limit: int = 50,
) -> list[dict]:
    """Stream Lichess puzzle DB and extract matching puzzles.

    Args:
        db_path: Path to lichess_db_puzzle.csv.zst
        themes: List of Lichess theme names to filter by
        min_rating: Minimum puzzle rating
        max_rating: Maximum puzzle rating
        min_popularity: Minimum popularity score (0-100)
        limit: Maximum puzzles to return

    Returns:
        List of chess_rocket-format puzzle dicts
    """
    if not db_path.exists():
        print(f"Error: {db_path} not found", file=sys.stderr)
        return []

    theme_set = set(themes)
    puzzles: list[dict] = []
    seen_fens: set[str] = set()
    rows_scanned = 0

    with open(db_path, "rb") as f:
        dctx = zstandard.ZstdDecompressor()
        reader = dctx.stream_reader(f)
        text = io.TextIOWrapper(reader, encoding="utf-8")
        csv_reader = csv.reader(text)

        # Skip header
        header = next(csv_reader, None)
        if header is None:
            return []

        for row in csv_reader:
            if len(puzzles) >= limit:
                break

            rows_scanned += 1
            if len(row) < 8:
                continue

            puzzle_id = row[0]
            game_fen = row[1]
            moves_str = row[2]
            try:
                rating = int(row[3])
                popularity = int(row[5])
            except (ValueError, IndexError):
                continue

            puzzle_themes = row[7].split() if row[7] else []

            # Filter by rating
            if rating < min_rating or rating > max_rating:
                continue

            # Filter by popularity
            if popularity < min_popularity:
                continue

            # Filter by theme - at least one requested theme must match
            matching_themes = theme_set & set(puzzle_themes)
            if not matching_themes:
                continue

            # Parse moves
            uci_moves = moves_str.split()
            if len(uci_moves) < 2:
                continue  # Need at least setup move + 1 solution move

            # Apply setup move to get puzzle position
            try:
                board = chess.Board(game_fen)
                setup_move = chess.Move.from_uci(uci_moves[0])
                if setup_move not in board.legal_moves:
                    continue
                board.push(setup_move)
            except (ValueError, IndexError):
                continue

            puzzle_fen = board.fen()

            # Deduplicate by normalized FEN
            norm_fen = _normalize_fen(puzzle_fen)
            if norm_fen in seen_fens:
                continue
            seen_fens.add(norm_fen)

            # Solution moves are moves[1:]
            solution_uci = uci_moves[1:]

            # Validate all solution moves are legal in sequence
            valid = True
            check_board = board.copy()
            for uci in solution_uci:
                try:
                    move = chess.Move.from_uci(uci)
                    if move not in check_board.legal_moves:
                        valid = False
                        break
                    check_board.push(move)
                except ValueError:
                    valid = False
                    break
            if not valid:
                continue

            # Pick motif from matched themes
            motif = _pick_motif(list(matching_themes))
            if motif is None:
                # Fallback: pick from all puzzle themes
                motif = _pick_motif(puzzle_themes)
            if motif is None:
                motif = "tactics"

            # Extra validation for checkmate/back-rank puzzles
            if motif == "checkmate" and not _validate_checkmate(board, solution_uci):
                continue
            if motif == "back_rank_mate":
                if not _validate_back_rank(board, solution_uci):
                    continue

            # Convert solution to SAN
            san_board = board.copy()
            solution_san = _moves_to_san(san_board, solution_uci)

            difficulty = _rating_to_difficulty(rating)
            explanation = EXPLANATION_TEMPLATES.get(
                motif, "Find the best move in this position!"
            )

            puzzle = {
                "fen": puzzle_fen,
                "solution_moves": solution_uci,
                "solution_san": solution_san,
                "motif": motif,
                "difficulty": difficulty,
                "difficulty_rating": rating,
                "explanation": explanation,
                "source": "lichess",
                "lichess_id": puzzle_id,
                "lichess_themes": puzzle_themes,
            }
            puzzles.append(puzzle)

    print(f"Scanned {rows_scanned} rows, found {len(puzzles)} matching puzzles",
          file=sys.stderr)
    return puzzles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import puzzles from Lichess puzzle database"
    )
    parser.add_argument(
        "--themes",
        type=str,
        required=True,
        help="Comma-separated Lichess theme names (e.g., mateIn1,backRankMate,fork)",
    )
    parser.add_argument(
        "--min-rating", type=int, default=0, help="Minimum puzzle rating (default: 0)"
    )
    parser.add_argument(
        "--max-rating",
        type=int,
        default=9999,
        help="Maximum puzzle rating (default: 9999)",
    )
    parser.add_argument(
        "--min-popularity",
        type=int,
        default=80,
        help="Minimum popularity score 0-100 (default: 80)",
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="Maximum puzzles to import (default: 50)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path (default: stdout)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(DEFAULT_DB),
        help=f"Path to lichess_db_puzzle.csv.zst (default: {DEFAULT_DB})",
    )
    args = parser.parse_args()

    themes = [t.strip() for t in args.themes.split(",") if t.strip()]
    if not themes:
        print("Error: --themes must specify at least one theme", file=sys.stderr)
        return 1

    db_path = Path(args.db)
    puzzles = import_puzzles(
        db_path=db_path,
        themes=themes,
        min_rating=args.min_rating,
        max_rating=args.max_rating,
        min_popularity=args.min_popularity,
        limit=args.limit,
    )

    if not puzzles:
        print("No matching puzzles found.", file=sys.stderr)
        return 1

    output_json = json.dumps(puzzles, indent=2)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_json + "\n")
        print(f"Wrote {len(puzzles)} puzzles to {args.output}", file=sys.stderr)
    else:
        print(output_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
