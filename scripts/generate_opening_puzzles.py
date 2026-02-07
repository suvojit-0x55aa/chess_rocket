#!/usr/bin/env python3
"""Generate opening-based puzzles: 'next book move' and 'opening trap' sets.

Usage:
    uv run python scripts/generate_opening_puzzles.py

Creates:
    puzzles/opening-moves.json  (~30 'next book move' knowledge tests)
    puzzles/opening-traps.json  (~20 opening trap refutation puzzles)
"""

import json
import os
import random
import sqlite3
import sys

import chess
import chess.engine
import chess.pgn

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
_DB_PATH = os.path.join(_PROJECT_ROOT, "data", "openings.db")
_PUZZLES_DIR = os.path.join(_PROJECT_ROOT, "puzzles")

# Seed for reproducibility
random.seed(42)


# ── Opening Moves Puzzles ───────────────────────────────────────────


def _pgn_to_moves(pgn_str):
    """Convert PGN string to list of chess.Move objects."""
    import io

    game = chess.pgn.read_game(io.StringIO(pgn_str))
    if game is None:
        return []
    return list(game.mainline_moves())


def _difficulty_from_halfmoves(n):
    """Classify difficulty based on position depth in half-moves."""
    if n <= 4:
        return "beginner"
    elif n <= 8:
        return "intermediate"
    else:
        return "advanced"


def generate_opening_moves_puzzles(conn):
    """Generate ~30 'next book move' puzzles across all ECO volumes.

    For each puzzle: position is after N-1 moves, solution is move N.
    """
    puzzles = []

    # Target ~6 puzzles per ECO volume
    for eco_volume in "ABCDE":
        rows = conn.execute(
            "SELECT * FROM openings WHERE eco_volume = ? AND num_moves >= 2 "
            "ORDER BY RANDOM()",
            (eco_volume,),
        ).fetchall()

        count = 0
        seen_fens = set()

        for row in rows:
            if count >= 7:
                break

            opening = dict(row)
            moves = _pgn_to_moves(opening["pgn"])
            if len(moves) < 2:
                continue

            # Pick a move index to quiz on (skip move 0 for trivial openings)
            # For variety, try different depths
            max_idx = len(moves) - 1
            if max_idx < 1:
                continue

            # Pick the last move as the quiz move (most specific to the opening)
            quiz_idx = max_idx

            # Build position up to quiz_idx - 1
            board = chess.Board()
            for m in moves[:quiz_idx]:
                board.push(m)

            fen = board.fen()
            if fen in seen_fens:
                continue
            seen_fens.add(fen)

            solution_move = moves[quiz_idx]
            if solution_move not in board.legal_moves:
                continue

            halfmoves = quiz_idx  # number of half-moves played before the quiz

            puzzle = {
                "fen": fen,
                "solution_moves": [solution_move.uci()],
                "solution_san": [board.san(solution_move)],
                "motif": "opening",
                "difficulty": _difficulty_from_halfmoves(halfmoves),
                "explanation": (
                    f"This is the book move in the {opening['name']} "
                    f"({opening['eco']}). {board.san(solution_move)} continues "
                    f"the opening theory."
                ),
            }
            puzzles.append(puzzle)
            count += 1

    return puzzles


# ── Opening Traps Puzzles ───────────────────────────────────────────

# Curated famous opening traps with hardcoded FENs and refutations
_CURATED_TRAPS = [
    {
        "fen": "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4",
        "solution_moves": ["h5f7"],
        "solution_san": ["Qxf7#"],
        "motif": "opening_trap",
        "difficulty": "beginner",
        "explanation": "Scholar's Mate: White's queen captures f7 with checkmate. "
        "Black failed to defend the f7 pawn after Bc4 and Qh5.",
    },
    {
        "fen": "rnbqkb1r/ppp2ppp/3p1n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4",
        "solution_moves": ["f3g5"],
        "solution_san": ["Ng5"],
        "motif": "opening_trap",
        "difficulty": "intermediate",
        "explanation": "Fried Liver Attack preparation: Ng5 targets the weak f7 "
        "square. After 4...d5 5.exd5 Nxd5 6.Nxf7! sacrifices the knight for a "
        "devastating attack on the exposed king.",
    },
    {
        "fen": "r1bqkbnr/pppppppp/2n5/8/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 2 2",
        "solution_moves": ["f7f5"],
        "solution_san": ["f5"],
        "motif": "opening_trap",
        "difficulty": "beginner",
        "explanation": "Fishing Pole Trap setup in Ruy Lopez: Black plays ...f5, "
        "inviting exf5 which opens lines against the white king. A common "
        "beginner trap that punishes greedy pawn grabbing.",
    },
    {
        "fen": "rnbqkbnr/pppp1ppp/8/4p3/4PP2/8/PPPP2PP/RNBQKBNR b KQkq - 0 2",
        "solution_moves": ["d8h4"],
        "solution_san": ["Qh4+"],
        "motif": "opening_trap",
        "difficulty": "beginner",
        "explanation": "King's Gambit trap: After 1.e4 e5 2.f4, Black plays "
        "Qh4+ giving check. White's king is exposed after f4 weakened the "
        "kingside. White cannot castle and the queen is very active.",
    },
    {
        "fen": "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2",
        "solution_moves": ["d8h4"],
        "solution_san": ["Qh4#"],
        "motif": "opening_trap",
        "difficulty": "beginner",
        "explanation": "Fool's Mate: After 1.f3 e5 2.g4, Black delivers checkmate "
        "with Qh4#. The fastest possible checkmate in chess.",
    },
    {
        "fen": "r1bqk1nr/pppp1ppp/2n5/2b1p3/2BPP3/5N2/PPP2PPP/RNBQK2R b KQkq - 0 4",
        "solution_moves": ["e5d4"],
        "solution_san": ["exd4"],
        "motif": "opening_trap",
        "difficulty": "intermediate",
        "explanation": "Legal's Mate preparation: In the Italian Game after d4, "
        "Black captures exd4. If Black gets greedy with ...Bxf2+, White can "
        "sacrifice the queen and deliver checkmate with the minor pieces.",
    },
    {
        "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        "solution_moves": ["e7e5"],
        "solution_san": ["e5"],
        "motif": "opening_trap",
        "difficulty": "beginner",
        "explanation": "Englund Gambit Trap avoidance: The principled response to "
        "1.e4 is 1...e5, controlling the center. Gambits like 1...e6 or 1...b6 "
        "can lead to traps for the unprepared.",
    },
    {
        "fen": "rnbqkbnr/pppp1ppp/8/8/2B1Pp2/8/PPPP2PP/RNBQK1NR b KQkq - 1 3",
        "solution_moves": ["d8h4"],
        "solution_san": ["Qh4+"],
        "motif": "opening_trap",
        "difficulty": "intermediate",
        "explanation": "King's Gambit Accepted trap: After 1.e4 e5 2.f4 exf4 "
        "3.Bc4??, Black plays Qh4+ with a powerful check. White's king is "
        "exposed and the position is very difficult to defend.",
    },
    {
        "fen": "rnbqkbnr/ppp2ppp/4p3/3pP3/3P4/8/PPP2PPP/RNBQKBNR b KQkq - 0 3",
        "solution_moves": ["c7c5"],
        "solution_san": ["c5"],
        "motif": "opening_trap",
        "difficulty": "intermediate",
        "explanation": "French Defense: Advance Variation. Black plays c5 to "
        "challenge White's pawn center. Failing to play c5 lets White build "
        "an overwhelming space advantage.",
    },
    {
        "fen": "rnbqkb1r/pppppppp/5n2/8/2PP4/8/PP2PPPP/RNBQKBNR b KQkq - 0 2",
        "solution_moves": ["e7e5"],
        "solution_san": ["e5"],
        "motif": "opening_trap",
        "difficulty": "intermediate",
        "explanation": "Budapest Gambit: After 1.d4 Nf6 2.c4, Black plays e5!? "
        "sacrificing a pawn for rapid development and tactical chances. "
        "White must be careful not to fall into the Kieninger Trap.",
    },
]


def _find_stockfish():
    """Find Stockfish binary path."""
    candidates = [
        "/opt/homebrew/bin/stockfish",
        "/usr/local/bin/stockfish",
        "/usr/bin/stockfish",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    import shutil

    sf = shutil.which("stockfish")
    if sf:
        return sf
    return None


def generate_auto_traps(conn):
    """Generate ~10 auto-detected opening traps using Stockfish.

    Finds positions where a 'natural' bad move leads to >= 150cp punishment.
    """
    sf_path = _find_stockfish()
    if not sf_path:
        print("WARNING: Stockfish not found, skipping auto-generated traps")
        return []

    engine = chess.engine.SimpleEngine.popen_uci(sf_path)
    traps = []
    seen_fens = set()

    try:
        # Get openings with 3-8 half-moves (good trap territory)
        rows = conn.execute(
            "SELECT * FROM openings WHERE num_moves BETWEEN 3 AND 8 "
            "ORDER BY RANDOM() LIMIT 200"
        ).fetchall()

        for row in rows:
            if len(traps) >= 12:
                break

            opening = dict(row)
            moves = _pgn_to_moves(opening["pgn"])
            if len(moves) < 3:
                continue

            board = chess.Board()
            for m in moves:
                board.push(m)

            # Analyze the position after the opening
            if board.is_game_over():
                continue

            legal = list(board.legal_moves)
            if len(legal) < 3:
                continue

            # Find the best move
            best_result = engine.analyse(board, chess.engine.Limit(depth=15))
            best_score = best_result.get("score")
            if best_score is None:
                continue

            best_cp = best_score.relative.score(mate_score=10000)
            if best_cp is None:
                continue

            best_move = best_result.get("pv", [None])[0]
            if best_move is None:
                continue

            # Try some natural-looking moves to find bad ones
            for candidate in random.sample(legal, min(5, len(legal))):
                if candidate == best_move:
                    continue

                board.push(candidate)
                if board.is_game_over():
                    board.pop()
                    continue

                after_result = engine.analyse(board, chess.engine.Limit(depth=15))
                after_score = after_result.get("score")
                board.pop()

                if after_score is None:
                    continue

                after_cp = after_score.relative.score(mate_score=10000)
                if after_cp is None:
                    continue

                # Score is from the OTHER side's perspective after the move
                # cp_loss = how much the moving side lost
                cp_loss = best_cp - (-after_cp)

                if cp_loss >= 150:
                    fen = board.fen()
                    if fen in seen_fens:
                        continue
                    seen_fens.add(fen)

                    # The "puzzle" is: find the best move (avoid the trap)
                    trap_puzzle = {
                        "fen": fen,
                        "solution_moves": [best_move.uci()],
                        "solution_san": [board.san(best_move)],
                        "motif": "opening_trap",
                        "difficulty": _difficulty_from_halfmoves(len(moves)),
                        "explanation": (
                            f"In the {opening['name']} ({opening['eco']}), "
                            f"the natural-looking {board.san(candidate)} is a "
                            f"mistake (loses ~{cp_loss}cp). The correct move is "
                            f"{board.san(best_move)}."
                        ),
                    }
                    traps.append(trap_puzzle)
                    break  # one trap per opening position

    finally:
        engine.quit()

    return traps


def generate_opening_traps_puzzles(conn):
    """Generate ~20 opening trap puzzles (curated + auto-generated)."""
    # Start with curated traps - validate each one
    valid_curated = []
    for trap in _CURATED_TRAPS:
        try:
            board = chess.Board(trap["fen"])
            move = chess.Move.from_uci(trap["solution_moves"][0])
            if move in board.legal_moves:
                valid_curated.append(trap)
            else:
                print(f"WARNING: Curated trap invalid move {trap['solution_moves'][0]} "
                      f"at FEN {trap['fen']}, skipping")
        except (ValueError, IndexError) as e:
            print(f"WARNING: Curated trap invalid: {e}, skipping")

    # Generate auto traps
    auto_traps = generate_auto_traps(conn)

    return valid_curated + auto_traps


# ── Main ────────────────────────────────────────────────────────────


def main():
    if not os.path.exists(_DB_PATH):
        print(
            "ERROR: Openings database not found. "
            "Run: uv run python scripts/build_openings_db.py"
        )
        sys.exit(1)

    os.makedirs(_PUZZLES_DIR, exist_ok=True)

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        print("Generating opening-moves puzzles...")
        moves_puzzles = generate_opening_moves_puzzles(conn)
        print(f"  Generated {len(moves_puzzles)} opening-moves puzzles")

        # Verify ECO volume coverage
        volumes = set()
        for p in moves_puzzles:
            eco = p["explanation"].split("(")[-1].split(")")[0]
            if len(eco) >= 1:
                volumes.add(eco[0])
        print(f"  ECO volumes covered: {sorted(volumes)}")

        moves_path = os.path.join(_PUZZLES_DIR, "opening-moves.json")
        with open(moves_path, "w", encoding="utf-8") as f:
            json.dump(moves_puzzles, f, indent=2, ensure_ascii=False)
        print(f"  Wrote {moves_path}")

        print("\nGenerating opening-traps puzzles...")
        traps_puzzles = generate_opening_traps_puzzles(conn)
        print(f"  Generated {len(traps_puzzles)} opening-traps puzzles "
              f"({len([t for t in traps_puzzles if t in _CURATED_TRAPS])} curated + "
              f"{len(traps_puzzles) - len(_CURATED_TRAPS)} auto)")

        traps_path = os.path.join(_PUZZLES_DIR, "opening-traps.json")
        with open(traps_path, "w", encoding="utf-8") as f:
            json.dump(traps_puzzles, f, indent=2, ensure_ascii=False)
        print(f"  Wrote {traps_path}")

    finally:
        conn.close()

    print("\nDone! Run 'uv run python scripts/validate_puzzles.py' to verify.")


if __name__ == "__main__":
    main()
