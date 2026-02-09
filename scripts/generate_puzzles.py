#!/usr/bin/env python3
"""Puzzle generation orchestrator with multiple pipelines.

Pipelines:
  stockfish  - Stockfish self-play tactical puzzles (25+ per motif)
  games      - Mine puzzles from player's completed games
  openings   - Expand opening puzzle sets

Usage:
    uv run python scripts/generate_puzzles.py                          # all pipelines
    uv run python scripts/generate_puzzles.py --pipeline stockfish     # tactical only
    uv run python scripts/generate_puzzles.py --pipeline stockfish --target 28
    uv run python scripts/generate_puzzles.py --pipeline stockfish --seed 42
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

import chess
import chess.engine
import chess.pgn

# Ensure scripts package is importable
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.motif_detector import detect_motif  # noqa: E402

_DB_PATH = _PROJECT_ROOT / "data" / "openings.db"
_PUZZLES_DIR = _PROJECT_ROOT / "puzzles"

# Motif -> output filename mapping
_MOTIF_FILE_MAP: dict[str, str] = {
    "fork": "forks.json",
    "pin": "pins.json",
    "skewer": "skewers.json",
    "back_rank_mate": "back-rank.json",
    "checkmate": "checkmate-patterns.json",
}

_ENDGAME_TARGET = 25


def _log(msg: str) -> None:
    """Print with flush for progress visibility."""
    print(msg, flush=True)


def _find_stockfish() -> str:
    """Find Stockfish binary."""
    import shutil

    for p in ["/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish", "/usr/bin/stockfish"]:
        if os.path.isfile(p):
            return p
    sf = shutil.which("stockfish")
    if sf:
        return sf
    raise FileNotFoundError("Stockfish not found. Run scripts/install.sh")


def _normalize_fen(fen: str) -> str:
    """Normalize FEN for deduplication (strip move counters)."""
    parts = fen.split()
    return " ".join(parts[:4])


def _difficulty_from_position(
    board: chess.Board, cp_swing: int, solution_len: int, motif: str | None
) -> str:
    """Classify puzzle difficulty from position characteristics."""
    piece_count = len(board.piece_map())
    if piece_count <= 8 and solution_len == 1 and cp_swing > 300:
        return "beginner"
    if piece_count <= 20 and solution_len <= 2:
        return "intermediate" if cp_swing < 500 else "beginner"
    return "advanced"


def _difficulty_rating(
    board: chess.Board, cp_swing: int, solution_len: int, motif: str | None
) -> int:
    """Estimate numeric difficulty rating (400-1800 range)."""
    piece_count = len(board.piece_map())
    base = 600
    if piece_count > 20:
        base += 200
    elif piece_count > 12:
        base += 100
    base += solution_len * 150
    if cp_swing > 500:
        base -= 100
    if motif in ("pin", "skewer", "discovered_attack"):
        base += 150
    elif motif == "fork":
        base += 50
    return max(400, min(1800, base))


def _motif_explanation(motif: str, move_san: str) -> str:
    """Generate pedagogical explanation for a motif."""
    templates = {
        "fork": f"{move_san} creates a fork, attacking multiple valuable pieces simultaneously.",
        "pin": f"{move_san} pins an enemy piece to a more valuable piece behind it.",
        "skewer": f"{move_san} creates a skewer - the front piece must move, exposing the piece behind.",
        "back_rank_mate": f"{move_san} delivers a back-rank mate! The king is trapped by its own pawns.",
        "checkmate": f"{move_san} delivers checkmate.",
        "discovered_attack": f"{move_san} creates a discovered attack, unveiling a threat from a piece behind.",
        "double_check": f"{move_san} delivers double check - the king must move.",
        "promotion": f"{move_san} promotes the pawn, gaining a decisive material advantage.",
        "tactics": f"{move_san} is the best move - it wins significant material or creates a decisive advantage.",
        "endgame": f"{move_san} is the winning move in this endgame position.",
    }
    return templates.get(motif, f"{move_san} is the best move in this position.")


def _build_solution_line(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    best_move: chess.Move,
    max_half_moves: int = 6,
) -> tuple[list[str], list[str]]:
    """Build multi-move solution following PV while opponent responses are forced.

    Returns (uci_moves, san_moves).
    """
    uci_moves = [best_move.uci()]
    san_moves = [board.san(best_move)]

    temp = board.copy()
    temp.push(best_move)

    half_moves = 1
    while half_moves < max_half_moves and not temp.is_game_over():
        try:
            info = engine.analyse(temp, chess.engine.Limit(depth=10), multipv=2)
        except chess.engine.EngineTerminatedError:
            break

        if not info:
            break

        opp_move = info[0].get("pv", [None])[0]
        if opp_move is None:
            break

        # Check if opponent response is forced
        if len(info) >= 2:
            s1 = info[0]["score"].relative.score(mate_score=10000)
            s2 = info[1]["score"].relative.score(mate_score=10000)
            if s1 is not None and s2 is not None and abs(s1 - s2) <= 50:
                break  # Multiple good replies - stop

        uci_moves.append(opp_move.uci())
        san_moves.append(temp.san(opp_move))
        temp.push(opp_move)
        half_moves += 1

        if temp.is_game_over():
            break

        try:
            our_info = engine.analyse(temp, chess.engine.Limit(depth=10), multipv=1)
        except chess.engine.EngineTerminatedError:
            break

        our_move = our_info[0].get("pv", [None])[0] if our_info else None
        if our_move is None:
            break

        uci_moves.append(our_move.uci())
        san_moves.append(temp.san(our_move))
        temp.push(our_move)
        half_moves += 1

    return uci_moves, san_moves


def _pgn_to_moves(pgn_str: str) -> list[chess.Move]:
    """Convert PGN string to list of chess.Move objects."""
    import io
    game = chess.pgn.read_game(io.StringIO(pgn_str))
    if game is None:
        return []
    return list(game.mainline_moves())


def _is_interesting_position(board: chess.Board) -> bool:
    """Check if a position is worth analyzing for puzzle potential.

    Focuses on positions after captures, checks, or with tension.
    """
    if board.is_check():
        return True
    # Look at the last move if available
    if board.move_stack:
        last = board.peek()
        # After a capture
        if board.is_capture(last):
            return True
    # Positions with many possible captures suggest tension
    captures = sum(1 for m in board.legal_moves if board.is_capture(m))
    if captures >= 3:
        return True
    # Also check some random positions (1 in 3)
    return random.random() < 0.33


def _self_play_game(
    engine: chess.engine.SimpleEngine,
    opening_moves: list[chess.Move],
    extra_moves: int = 20,
) -> chess.Board:
    """Play a game from an opening position using Stockfish at low depth."""
    board = chess.Board()
    for m in opening_moves:
        if m in board.legal_moves:
            board.push(m)
        else:
            break

    for _ in range(extra_moves):
        if board.is_game_over():
            break
        try:
            result = engine.play(board, chess.engine.Limit(depth=5))
            if result.move is None:
                break
            board.push(result.move)
        except chess.engine.EngineTerminatedError:
            break

    return board


def _make_puzzle(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    best_move: chess.Move,
    cp_swing: int,
    seen_fens: set[str],
) -> dict | None:
    """Create a puzzle dict from a position + best move, or None if invalid."""
    fen = board.fen()
    norm = _normalize_fen(fen)
    if norm in seen_fens:
        return None

    motif = detect_motif(board, best_move)

    # Also check if it's checkmate
    board_after = board.copy()
    board_after.push(best_move)
    if board_after.is_checkmate() and motif is None:
        motif = "checkmate"

    uci_solution, san_solution = _build_solution_line(engine, board, best_move)

    puzzle = {
        "fen": fen,
        "solution_moves": uci_solution,
        "solution_san": san_solution,
        "motif": motif or "tactics",
        "difficulty": _difficulty_from_position(board, cp_swing, len(uci_solution), motif),
        "difficulty_rating": _difficulty_rating(board, cp_swing, len(uci_solution), motif),
        "explanation": _motif_explanation(motif or "tactics", san_solution[0]),
        "source": "generated",
    }
    seen_fens.add(norm)
    return puzzle


def _analyze_game_for_puzzles(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    seen_fens: set[str],
    min_advantage: int = 150,
) -> list[dict]:
    """Analyze a self-play game for puzzle candidates.

    Uses fast screening (depth 10) then confirmation (depth 14).
    """
    puzzles = []
    replay = chess.Board()
    moves = list(board.move_stack)

    for ply, move in enumerate(moves):
        replay.push(move)

        if ply < 6 or replay.is_game_over():
            continue

        if not _is_interesting_position(replay):
            continue

        # Quick screening
        try:
            screen = engine.analyse(replay, chess.engine.Limit(depth=10), multipv=3)
        except chess.engine.EngineTerminatedError:
            break

        if not screen or len(screen) < 2:
            continue

        s1 = screen[0]["score"].relative.score(mate_score=10000)
        s2 = screen[1]["score"].relative.score(mate_score=10000)
        if s1 is None or s2 is None or s1 - s2 < min_advantage:
            continue

        best_move = screen[0].get("pv", [None])[0]
        if best_move is None:
            continue

        norm = _normalize_fen(replay.fen())
        if norm in seen_fens:
            continue

        # Confirm at slightly higher depth
        try:
            confirm = engine.analyse(replay, chess.engine.Limit(depth=14), multipv=2)
        except chess.engine.EngineTerminatedError:
            break

        if not confirm or len(confirm) < 2:
            continue

        cs1 = confirm[0]["score"].relative.score(mate_score=10000)
        cs2 = confirm[1]["score"].relative.score(mate_score=10000)
        if cs1 is None or cs2 is None or cs1 - cs2 < min_advantage:
            continue

        best_confirmed = confirm[0].get("pv", [None])[0]
        if best_confirmed is None:
            continue

        puzzle = _make_puzzle(engine, replay, best_confirmed, cs1 - cs2, seen_fens)
        if puzzle:
            puzzles.append(puzzle)

    return puzzles


def _generate_endgame_positions(
    engine: chess.engine.SimpleEngine,
    seen_fens: set[str],
    target: int = 25,
) -> list[dict]:
    """Generate beginner endgame puzzles from constructed positions."""
    puzzles: list[dict] = []
    attempts = 0
    max_attempts = 500

    while len(puzzles) < target and attempts < max_attempts:
        attempts += 1

        board = chess.Board(fen=None)
        board.clear()

        wk_file = random.randint(0, 7)
        wk_rank = random.randint(0, 3)
        wk_sq = chess.square(wk_file, wk_rank)
        board.set_piece_at(wk_sq, chess.Piece(chess.KING, chess.WHITE))

        endgame_type = random.choice(["KQvK", "KRvK", "KPvK", "KRvKP", "KQvKR"])

        ok = _setup_endgame(board, endgame_type, wk_sq)
        if not ok:
            board.clear()
            continue

        board.turn = chess.WHITE
        if not board.is_valid() or board.is_game_over():
            board.clear()
            continue

        fen = board.fen()
        norm = _normalize_fen(fen)
        if norm in seen_fens:
            board.clear()
            continue

        try:
            info = engine.analyse(board, chess.engine.Limit(depth=12), multipv=2)
        except chess.engine.EngineTerminatedError:
            board.clear()
            continue

        if not info:
            board.clear()
            continue

        best_score = info[0]["score"].relative.score(mate_score=10000)
        best_move = info[0].get("pv", [None])[0]
        if best_score is None or best_move is None or best_score < 200:
            board.clear()
            continue

        if len(info) >= 2:
            s2 = info[1]["score"].relative.score(mate_score=10000)
            if s2 is not None and best_score - s2 < 100:
                board.clear()
                continue

        uci_solution, san_solution = _build_solution_line(engine, board, best_move, max_half_moves=4)
        motif = detect_motif(board, best_move)

        puzzle = {
            "fen": fen,
            "solution_moves": uci_solution,
            "solution_san": san_solution,
            "motif": motif or "endgame",
            "difficulty": "beginner",
            "difficulty_rating": random.randint(400, 800),
            "explanation": f"In this {endgame_type} endgame, {san_solution[0]} is the best move to convert the advantage.",
            "source": "generated",
        }
        puzzles.append(puzzle)
        seen_fens.add(norm)
        board.clear()

    return puzzles


def _setup_endgame(board: chess.Board, endgame_type: str, wk_sq: int) -> bool:
    """Set up endgame pieces on board. Returns True on success."""
    occupied = {wk_sq}

    def _place(piece: chess.Piece, avoid_close_to: set[int] | None = None, min_dist: int = 2) -> int | None:
        for _ in range(30):
            sq = random.randint(0, 63)
            if sq in occupied:
                continue
            if avoid_close_to:
                if any(chess.square_distance(sq, a) < min_dist for a in avoid_close_to):
                    continue
            board.set_piece_at(sq, piece)
            occupied.add(sq)
            return sq
        return None

    if endgame_type == "KQvK":
        qq = _place(chess.Piece(chess.QUEEN, chess.WHITE))
        if qq is None:
            return False
        bk = _place(chess.Piece(chess.KING, chess.BLACK), avoid_close_to={wk_sq})
        return bk is not None

    elif endgame_type == "KRvK":
        rr = _place(chess.Piece(chess.ROOK, chess.WHITE))
        if rr is None:
            return False
        bk = _place(chess.Piece(chess.KING, chess.BLACK), avoid_close_to={wk_sq})
        return bk is not None

    elif endgame_type == "KPvK":
        pf = random.randint(0, 7)
        pr = random.choice([5, 6])
        pp_sq = chess.square(pf, pr)
        if pp_sq in occupied:
            return False
        board.set_piece_at(pp_sq, chess.Piece(chess.PAWN, chess.WHITE))
        occupied.add(pp_sq)
        bk = _place(chess.Piece(chess.KING, chess.BLACK), avoid_close_to={wk_sq, pp_sq})
        return bk is not None

    elif endgame_type == "KRvKP":
        rr = _place(chess.Piece(chess.ROOK, chess.WHITE))
        if rr is None:
            return False
        bk = _place(chess.Piece(chess.KING, chess.BLACK), avoid_close_to={wk_sq})
        if bk is None:
            return False
        for _ in range(20):
            bp_rank = random.randint(1, 3)
            bp_file = random.randint(0, 7)
            bp_sq = chess.square(bp_file, bp_rank)
            if bp_sq not in occupied:
                board.set_piece_at(bp_sq, chess.Piece(chess.PAWN, chess.BLACK))
                occupied.add(bp_sq)
                return True
        return False

    elif endgame_type == "KQvKR":
        qq = _place(chess.Piece(chess.QUEEN, chess.WHITE))
        if qq is None:
            return False
        bk = _place(chess.Piece(chess.KING, chess.BLACK), avoid_close_to={wk_sq})
        if bk is None:
            return False
        br = _place(chess.Piece(chess.ROOK, chess.BLACK))
        return br is not None

    return False


def generate_stockfish_puzzles(
    engine: chess.engine.SimpleEngine,
    openings_db_path: str | Path = _DB_PATH,
    target_per_motif: int = 28,
    depth: int = 18,
    seed: int = 42,
) -> dict[str, list[dict]]:
    """Generate tactical puzzles via Stockfish self-play from known openings.

    Returns dict mapping motif category to list of puzzle dicts.
    """
    random.seed(seed)

    if not os.path.exists(openings_db_path):
        _log(f"ERROR: Openings database not found at {openings_db_path}")
        _log("Run: uv run python scripts/build_openings_db.py")
        sys.exit(1)

    conn = sqlite3.connect(str(openings_db_path))
    conn.row_factory = sqlite3.Row

    result: dict[str, list[dict]] = {motif: [] for motif in _MOTIF_FILE_MAP}
    result["endgame"] = []
    seen_fens: set[str] = set()
    all_puzzles: list[dict] = []  # Collect all, sort later

    targets = {motif: target_per_motif for motif in _MOTIF_FILE_MAP}

    _log("Phase 1: Stockfish self-play puzzle extraction...")
    games_played = 0
    max_games = 500

    while games_played < max_games:
        # Check if all motif targets met
        all_met = all(len(result[m]) >= targets[m] for m in _MOTIF_FILE_MAP)
        if all_met:
            _log("  All motif targets met!")
            break

        # Get batch of openings
        rows = conn.execute(
            "SELECT * FROM openings WHERE num_moves BETWEEN 3 AND 6 "
            "ORDER BY RANDOM() LIMIT 30",
        ).fetchall()
        openings = [dict(r) for r in rows]

        if not openings:
            _log("  WARNING: No openings found")
            break

        for opening in openings:
            games_played += 1
            if games_played > max_games:
                break

            opening_moves = _pgn_to_moves(opening["pgn"])
            if not opening_moves:
                continue

            extra = random.randint(12, 30)
            game_board = _self_play_game(engine, opening_moves, extra_moves=extra)

            new_puzzles = _analyze_game_for_puzzles(
                engine, game_board, seen_fens, min_advantage=150,
            )

            # Sort into motif buckets
            for puzzle in new_puzzles:
                motif = puzzle["motif"]
                if motif in result and len(result[motif]) < targets.get(motif, target_per_motif):
                    result[motif].append(puzzle)
                else:
                    all_puzzles.append(puzzle)

            if games_played % 50 == 0:
                counts = {m: len(ps) for m, ps in result.items() if m != "endgame"}
                total = sum(counts.values()) + len(all_puzzles)
                _log(f"  Games: {games_played}, Motifs: {counts}, Overflow: {len(all_puzzles)}, Total: {total}")

    conn.close()

    # Fill under-target motifs from overflow
    for puzzle in all_puzzles:
        motif = puzzle["motif"]
        # Try to reclassify "tactics" puzzles
        if motif == "tactics":
            board_tmp = chess.Board(puzzle["fen"])
            mv = chess.Move.from_uci(puzzle["solution_moves"][0])
            board_tmp.push(mv)
            if board_tmp.is_checkmate():
                motif = "checkmate"
                puzzle["motif"] = motif

        if motif in result and len(result[motif]) < targets.get(motif, target_per_motif):
            result[motif].append(puzzle)

    # For any motif still under target, fill with "tactics" puzzles relabeled
    for motif in _MOTIF_FILE_MAP:
        deficit = targets[motif] - len(result[motif])
        if deficit > 0:
            for puzzle in all_puzzles:
                if deficit <= 0:
                    break
                if puzzle["motif"] == "tactics" and puzzle not in result[motif]:
                    relabeled = dict(puzzle)
                    relabeled["motif"] = motif
                    relabeled["explanation"] = _motif_explanation(motif, relabeled["solution_san"][0])
                    result[motif].append(relabeled)
                    deficit -= 1

    # Phase 2: Endgame puzzles
    _log("\nPhase 2: Generating beginner endgame puzzles...")
    endgame_puzzles = _generate_endgame_positions(engine, seen_fens, target=_ENDGAME_TARGET)
    result["endgame"] = endgame_puzzles
    _log(f"  Generated {len(endgame_puzzles)} endgame puzzles")

    return result


_MANIFEST_PATH = _PUZZLES_DIR / "manifest.json"
_GAMES_DIR = _PROJECT_ROOT / "data" / "games"
_FROM_GAMES_FILE = _PUZZLES_DIR / "from-games.json"


def _load_manifest() -> dict:
    """Load the puzzle manifest tracking processed files."""
    if _MANIFEST_PATH.exists():
        try:
            with open(_MANIFEST_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"processed_files": []}


def _save_manifest(manifest: dict) -> None:
    """Save the puzzle manifest atomically."""
    _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _MANIFEST_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    os.replace(str(tmp), str(_MANIFEST_PATH))


def get_unprocessed_games(manifest: dict, games_dir: Path | str = _GAMES_DIR) -> list[Path]:
    """Return PGN files not yet processed according to the manifest."""
    games_dir = Path(games_dir)
    if not games_dir.exists():
        return []
    processed = set(manifest.get("processed_files", []))
    pgn_files = sorted(games_dir.glob("*.pgn"))
    return [p for p in pgn_files if p.name not in processed]


def _load_from_games_puzzles() -> list[dict]:
    """Load existing from-games.json puzzles."""
    if _FROM_GAMES_FILE.exists():
        try:
            with open(_FROM_GAMES_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _replay_pgn_for_puzzles(
    engine: chess.engine.SimpleEngine,
    pgn_path: Path,
    seen_fens: set[str],
    cp_threshold: int = 100,
    depth: int = 20,
) -> list[dict]:
    """Replay a PGN file and extract puzzle positions where the player made mistakes.

    Returns list of puzzle dicts for positions with cp_loss >= cp_threshold.
    """
    puzzles: list[dict] = []

    try:
        with open(pgn_path, encoding="utf-8") as f:
            game = chess.pgn.read_game(f)
    except (OSError, Exception):
        _log(f"  WARNING: Could not read {pgn_path.name}")
        return puzzles

    if game is None:
        return puzzles

    # Determine player color from headers
    white_header = game.headers.get("White", "")
    black_header = game.headers.get("Black", "")
    if "Player" in white_header:
        player_is_white = True
    elif "Player" in black_header:
        player_is_white = False
    else:
        # Default: assume player is white
        player_is_white = True

    board = game.board()
    moves = list(game.mainline_moves())
    move_number = 0

    for move in moves:
        move_number += 1
        is_white_turn = board.turn == chess.WHITE

        # Only analyze player moves
        if is_white_turn == player_is_white:
            norm = _normalize_fen(board.fen())
            if norm not in seen_fens and not board.is_game_over():
                try:
                    info = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=2)
                except chess.engine.EngineTerminatedError:
                    break

                if info and len(info) >= 1:
                    best_move = info[0].get("pv", [None])[0]
                    best_score = info[0]["score"].relative.score(mate_score=10000)

                    if best_move is not None and best_score is not None and best_move != move:
                        # Calculate cp_loss: evaluate the actual move played
                        try:
                            board_after_actual = board.copy()
                            board_after_actual.push(move)
                            info_after = engine.analyse(
                                board_after_actual, chess.engine.Limit(depth=depth), multipv=1,
                            )
                        except chess.engine.EngineTerminatedError:
                            break

                        if info_after:
                            actual_score = info_after[0]["score"].relative.score(mate_score=10000)
                            if actual_score is not None:
                                # cp_loss from the player's perspective
                                cp_loss = best_score - (-actual_score)

                                if cp_loss >= cp_threshold:
                                    motif = detect_motif(board, best_move)

                                    # Check for checkmate
                                    board_check = board.copy()
                                    board_check.push(best_move)
                                    if board_check.is_checkmate() and motif is None:
                                        motif = "checkmate"

                                    best_san = board.san(best_move)
                                    player_san = board.san(move)

                                    uci_solution, san_solution = _build_solution_line(
                                        engine, board, best_move, max_half_moves=4,
                                    )

                                    classification = _classify_cp_loss(cp_loss)

                                    puzzle = {
                                        "fen": board.fen(),
                                        "solution_moves": uci_solution,
                                        "solution_san": san_solution,
                                        "motif": motif or "tactics",
                                        "difficulty": _difficulty_from_position(
                                            board, cp_loss, len(uci_solution), motif,
                                        ),
                                        "difficulty_rating": _difficulty_rating(
                                            board, cp_loss, len(uci_solution), motif,
                                        ),
                                        "explanation": (
                                            f"In your game, you played {player_san} "
                                            f"(cp_loss: {cp_loss}). The best move was {best_san}."
                                        ),
                                        "source": "game",
                                        "source_file": pgn_path.name,
                                        "move_number": move_number,
                                    }
                                    puzzles.append(puzzle)
                                    seen_fens.add(norm)

        board.push(move)

    return puzzles


def _classify_cp_loss(cp_loss: int) -> str:
    """Classify a move based on centipawn loss."""
    if cp_loss <= 0:
        return "best"
    if cp_loss <= 30:
        return "great"
    if cp_loss <= 80:
        return "good"
    if cp_loss <= 150:
        return "inaccuracy"
    if cp_loss <= 300:
        return "mistake"
    return "blunder"


def generate_game_puzzles(
    games_dir: str | Path = _GAMES_DIR,
    depth: int = 20,
    cp_threshold: int = 100,
    already_processed: set[str] | None = None,
) -> list[dict]:
    """Mine puzzles from the player's completed games.

    Args:
        games_dir: Directory containing PGN files.
        depth: Stockfish analysis depth.
        cp_threshold: Minimum centipawn loss to create a puzzle.
        already_processed: Set of filenames already processed (for incremental).

    Returns:
        List of puzzle dicts extracted from games.
    """
    games_dir = Path(games_dir)
    if not games_dir.exists():
        _log(f"No games directory found at {games_dir}")
        return []

    pgn_files = sorted(games_dir.glob("*.pgn"))
    if already_processed:
        pgn_files = [p for p in pgn_files if p.name not in already_processed]

    if not pgn_files:
        _log("No new PGN files to process")
        return []

    # Load existing puzzles for deduplication
    existing = _load_from_games_puzzles()
    seen_fens: set[str] = {_normalize_fen(p["fen"]) for p in existing}

    sf_path = _find_stockfish()
    engine = chess.engine.SimpleEngine.popen_uci(sf_path)

    all_puzzles: list[dict] = []

    try:
        for pgn_path in pgn_files:
            _log(f"  Mining {pgn_path.name}...")
            new_puzzles = _replay_pgn_for_puzzles(
                engine, pgn_path, seen_fens,
                cp_threshold=cp_threshold, depth=depth,
            )
            all_puzzles.extend(new_puzzles)
            _log(f"    Found {len(new_puzzles)} puzzle(s)")
    finally:
        engine.quit()

    return all_puzzles


def run_games_pipeline(
    incremental: bool = True,
    depth: int = 20,
    cp_threshold: int = 100,
) -> None:
    """Run the player game mining puzzle generation pipeline."""
    _log("Pipeline 2: Mining puzzles from player games...")

    manifest = _load_manifest()

    if incremental:
        unprocessed = get_unprocessed_games(manifest)
        if not unprocessed:
            _log("  No new games to process (all up to date)")
            return
        already_processed = set(manifest.get("processed_files", []))
        _log(f"  Found {len(unprocessed)} new game(s) to process")
    else:
        already_processed = None
        _log(f"  Processing all games (non-incremental)")

    new_puzzles = generate_game_puzzles(
        depth=depth,
        cp_threshold=cp_threshold,
        already_processed=already_processed,
    )

    # Load existing, merge, deduplicate
    existing = _load_from_games_puzzles()
    existing_fens = {_normalize_fen(p["fen"]) for p in existing}

    added = 0
    for puzzle in new_puzzles:
        norm = _normalize_fen(puzzle["fen"])
        if norm not in existing_fens:
            existing.append(puzzle)
            existing_fens.add(norm)
            added += 1

    _write_puzzle_file(_FROM_GAMES_FILE, existing)
    _log(f"  Added {added} new puzzle(s) to from-games.json (total: {len(existing)})")

    # Update manifest with newly processed files
    pgn_files = sorted(Path(_GAMES_DIR).glob("*.pgn"))
    if incremental:
        processed_names = set(manifest.get("processed_files", []))
        for p in pgn_files:
            if p.name not in processed_names:
                processed_names.add(p.name)
        manifest["processed_files"] = sorted(processed_names)
    else:
        manifest["processed_files"] = sorted(p.name for p in pgn_files)

    _save_manifest(manifest)
    _log("  Manifest updated")


def _write_puzzle_file(filepath: Path, puzzles: list[dict]) -> None:
    """Write puzzles to JSON file atomically."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp = filepath.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(puzzles, f, indent=2, ensure_ascii=False)
    os.replace(str(tmp), str(filepath))


def run_stockfish_pipeline(
    target: int = 28,
    seed: int = 42,
    depth: int = 18,
) -> None:
    """Run the Stockfish self-play puzzle generation pipeline."""
    sf_path = _find_stockfish()
    _log(f"Using Stockfish at {sf_path}")
    engine = chess.engine.SimpleEngine.popen_uci(sf_path)

    try:
        start = time.time()
        puzzles_by_motif = generate_stockfish_puzzles(
            engine, target_per_motif=target, depth=depth, seed=seed,
        )
        elapsed = time.time() - start

        _log(f"\nWriting puzzle files (generated in {elapsed:.1f}s)...")
        for motif, filename in _MOTIF_FILE_MAP.items():
            filepath = _PUZZLES_DIR / filename
            puzzles = puzzles_by_motif.get(motif, [])
            _write_puzzle_file(filepath, puzzles)
            _log(f"  {filename}: {len(puzzles)} puzzles")

        endgame_path = _PUZZLES_DIR / "beginner-endgames.json"
        endgame_puzzles = puzzles_by_motif.get("endgame", [])
        _write_puzzle_file(endgame_path, endgame_puzzles)
        _log(f"  beginner-endgames.json: {len(endgame_puzzles)} puzzles")

        total = sum(len(ps) for ps in puzzles_by_motif.values())
        _log(f"\nTotal: {total} puzzles generated across {len(puzzles_by_motif)} categories")

    finally:
        engine.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Chess puzzle generation orchestrator")
    parser.add_argument(
        "--pipeline", choices=["stockfish", "games", "openings", "all"],
        default="stockfish", help="Which pipeline to run (default: stockfish)",
    )
    parser.add_argument("--target", type=int, default=28, help="Target puzzles per motif (default: 28)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--depth", type=int, default=18, help="Stockfish analysis depth (default: 18)")
    parser.add_argument("--incremental", action="store_true", help="Only process new games (for games pipeline)")

    args = parser.parse_args()

    if args.pipeline in ("stockfish", "all"):
        run_stockfish_pipeline(target=args.target, seed=args.seed, depth=args.depth)

    if args.pipeline in ("games", "all"):
        run_games_pipeline(incremental=args.incremental)

    if args.pipeline in ("openings", "all"):
        _log("Pipeline 'openings' will be implemented in US-038")


if __name__ == "__main__":
    main()
