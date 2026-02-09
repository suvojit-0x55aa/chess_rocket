"""Tactical motif detection for chess positions.

Programmatically identifies tactical themes (fork, pin, skewer,
back-rank mate, discovered attack, etc.) from a board position
and a move. Used by puzzle generators for auto-classification.
"""

from __future__ import annotations

import chess


# Piece values for tactical significance checks
_PIECE_VALUES: dict[int, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 100,
}


def _piece_value(piece_type: int) -> int:
    """Return the standard piece value for a piece type."""
    return _PIECE_VALUES.get(piece_type, 0)


def _detect_fork(board: chess.Board, move: chess.Move) -> bool:
    """Detect if the move creates a fork.

    A fork occurs when the moved piece attacks 2+ enemy pieces
    each worth >= knight value (3 points).
    """
    board_after = board.copy()
    board_after.push(move)

    to_sq = move.to_square
    moved_piece = board_after.piece_at(to_sq)
    if moved_piece is None:
        return False

    attacker_color = moved_piece.color
    enemy_color = not attacker_color

    # Find valuable enemy pieces attacked by the moved piece
    attacked_valuable = 0
    attacks = board_after.attacks(to_sq)
    for sq in attacks:
        victim = board_after.piece_at(sq)
        if victim is not None and victim.color == enemy_color:
            if _piece_value(victim.piece_type) >= 3:
                attacked_valuable += 1

    return attacked_valuable >= 2


def _detect_pin(board: chess.Board, move: chess.Move) -> bool:
    """Detect if the move creates a pin.

    A pin occurs when a sliding piece (bishop, rook, queen) pins
    an enemy piece to their king or queen.
    """
    board_after = board.copy()
    board_after.push(move)

    to_sq = move.to_square
    moved_piece = board_after.piece_at(to_sq)
    if moved_piece is None:
        return False

    # Only sliding pieces can pin
    if moved_piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False

    attacker_color = moved_piece.color
    enemy_color = not attacker_color

    # Check each enemy piece to see if it's pinned to king or queen
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece is None or piece.color != enemy_color:
            continue
        if piece.piece_type in (chess.KING, chess.QUEEN):
            continue

        # Check if this piece is pinned by our moved piece
        if board_after.is_pinned(enemy_color, sq):
            # Verify the pinner is our moved piece by checking the pin ray
            pin_mask = board_after.pin(enemy_color, sq)
            if pin_mask & chess.BB_SQUARES[to_sq]:
                return True

    return False


def _detect_skewer(board: chess.Board, move: chess.Move) -> bool:
    """Detect if the move creates a skewer.

    A skewer occurs when a sliding piece attacks a valuable piece
    with a less valuable piece behind it on the same ray.
    """
    board_after = board.copy()
    board_after.push(move)

    to_sq = move.to_square
    moved_piece = board_after.piece_at(to_sq)
    if moved_piece is None:
        return False

    if moved_piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False

    attacker_color = moved_piece.color
    enemy_color = not attacker_color

    # Check ray directions from the moved piece
    ray_directions = []
    if moved_piece.piece_type in (chess.ROOK, chess.QUEEN):
        ray_directions.extend(_ROOK_DIRECTIONS)
    if moved_piece.piece_type in (chess.BISHOP, chess.QUEEN):
        ray_directions.extend(_BISHOP_DIRECTIONS)

    for d_rank, d_file in ray_directions:
        pieces_on_ray = _scan_ray(board_after, to_sq, d_rank, d_file, enemy_color)
        if len(pieces_on_ray) >= 2:
            front_type = pieces_on_ray[0][1]
            back_type = pieces_on_ray[1][1]
            if _piece_value(front_type) > _piece_value(back_type):
                return True

    return False


# Ray direction vectors
_ROOK_DIRECTIONS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
_BISHOP_DIRECTIONS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]


def _scan_ray(
    board: chess.Board,
    from_sq: int,
    d_rank: int,
    d_file: int,
    target_color: chess.Color,
) -> list[tuple[int, int]]:
    """Scan along a ray and return enemy pieces found (square, piece_type)."""
    result: list[tuple[int, int]] = []
    rank = chess.square_rank(from_sq)
    file = chess.square_file(from_sq)

    rank += d_rank
    file += d_file

    while 0 <= rank <= 7 and 0 <= file <= 7:
        sq = chess.square(file, rank)
        piece = board.piece_at(sq)
        if piece is not None:
            if piece.color == target_color:
                result.append((sq, piece.piece_type))
            else:
                # Friendly piece blocks the ray
                break
        rank += d_rank
        file += d_file

    return result


def _detect_back_rank_mate(board: chess.Board, move: chess.Move) -> bool:
    """Detect if the move delivers a back-rank mate.

    Back-rank mate: checkmate on 1st or 8th rank where king is
    trapped by own pawns.
    """
    board_after = board.copy()
    board_after.push(move)

    if not board_after.is_checkmate():
        return False

    # Find the mated king
    mated_color = board_after.turn  # side to move is in checkmate
    king_sq = board_after.king(mated_color)
    if king_sq is None:
        return False

    king_rank = chess.square_rank(king_sq)

    # King must be on 1st or 8th rank
    if mated_color == chess.WHITE and king_rank != 0:
        return False
    if mated_color == chess.BLACK and king_rank != 7:
        return False

    # The checking piece must be on the back rank (delivering mate along the rank)
    checkers = board_after.checkers()
    checker_on_back_rank = False
    for sq in checkers:
        if chess.square_rank(sq) == king_rank:
            checker_on_back_rank = True
            break
    if not checker_on_back_rank:
        return False

    # Check if own pawns block escape
    escape_rank = 1 if mated_color == chess.WHITE else 6
    king_file = chess.square_file(king_sq)

    pawn_blocking = False
    for f in range(max(0, king_file - 1), min(8, king_file + 2)):
        sq = chess.square(f, escape_rank)
        piece = board_after.piece_at(sq)
        if piece is not None and piece.color == mated_color and piece.piece_type == chess.PAWN:
            pawn_blocking = True
            break

    return pawn_blocking


def _detect_discovered_attack(board: chess.Board, move: chess.Move) -> bool:
    """Detect if the move creates a discovered attack.

    A discovered attack occurs when moving a piece unblocks a ray
    from another friendly piece that now attacks an enemy piece.
    """
    from_sq = move.from_square
    to_sq = move.to_square
    moving_piece = board.piece_at(from_sq)
    if moving_piece is None:
        return False

    attacker_color = moving_piece.color
    enemy_color = not attacker_color

    board_after = board.copy()
    board_after.push(move)

    # Check if any friendly sliding piece now attacks through the vacated square
    for sq in chess.SQUARES:
        piece = board_after.piece_at(sq)
        if piece is None or piece.color != attacker_color:
            continue
        if sq == to_sq:
            continue  # Skip the moved piece itself
        if piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue

        # Did this piece's attack ray pass through from_sq before the move?
        # Check: does this piece now attack squares it didn't before,
        # and did from_sq block its ray?
        attacks_before = board.attacks(sq)
        attacks_after = board_after.attacks(sq)
        new_attacks = attacks_after & ~attacks_before

        if not new_attacks:
            continue

        # Check if the newly attacked squares include valuable enemy pieces
        for attacked_sq in new_attacks:
            victim = board_after.piece_at(attacked_sq)
            if victim is not None and victim.color == enemy_color:
                if _piece_value(victim.piece_type) >= 3:
                    return True

    return False


def _detect_double_check(board: chess.Board, move: chess.Move) -> bool:
    """Detect if the move delivers double check."""
    board_after = board.copy()
    board_after.push(move)

    if not board_after.is_check():
        return False

    return len(board_after.checkers()) >= 2


def _detect_promotion(board: chess.Board, move: chess.Move) -> bool:
    """Detect if the move is a promotion."""
    return move.promotion is not None


def _detect_checkmate(board: chess.Board, move: chess.Move) -> bool:
    """Detect if the move delivers checkmate."""
    board_after = board.copy()
    board_after.push(move)
    return board_after.is_checkmate()


def detect_all_motifs(board: chess.Board, move: chess.Move) -> list[str]:
    """Detect all tactical motifs present in the given move.

    Args:
        board: Board position BEFORE the move is made.
        move: The move to analyze.

    Returns:
        List of motif name strings. Empty list if no tactical theme.
    """
    motifs: list[str] = []

    # Order: most specific first
    if _detect_checkmate(board, move):
        if _detect_back_rank_mate(board, move):
            motifs.append("back_rank_mate")
        else:
            motifs.append("checkmate")

    if _detect_double_check(board, move):
        motifs.append("double_check")

    if _detect_discovered_attack(board, move):
        motifs.append("discovered_attack")

    if _detect_fork(board, move):
        motifs.append("fork")

    if _detect_pin(board, move):
        motifs.append("pin")

    if _detect_skewer(board, move):
        motifs.append("skewer")

    if _detect_promotion(board, move):
        motifs.append("promotion")

    return motifs


def detect_motif(board: chess.Board, move: chess.Move) -> str | None:
    """Detect the primary tactical motif for the given move.

    Args:
        board: Board position BEFORE the move is made.
        move: The move to analyze.

    Returns:
        The primary motif name string, or None for quiet/positional moves.
    """
    motifs = detect_all_motifs(board, move)
    return motifs[0] if motifs else None
