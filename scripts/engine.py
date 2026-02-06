"""Chess engine wrapper with adaptive difficulty for Chess Speedrun.

Wraps Stockfish via python-chess UCI interface. Provides:
- Adaptive difficulty (sub-1320 uses depth + random blend)
- Full-strength analysis independent of difficulty
- Move evaluation with classification
- CLI for quick analysis and play demos
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import chess
import chess.engine

from scripts.models import MoveEvaluation

if TYPE_CHECKING:
    pass

# Stockfish search paths in priority order
_STOCKFISH_PATHS = [
    "/opt/homebrew/bin/stockfish",
    "/usr/local/bin/stockfish",
    "/usr/bin/stockfish",
]

# Move classification thresholds (cp_loss -> classification)
_CLASSIFICATION_THRESHOLDS = [
    (0, "best"),
    (30, "great"),
    (80, "good"),
    (150, "inaccuracy"),
    (300, "mistake"),
]

_MATE_SCORE = 10000


def _find_stockfish() -> str:
    """Auto-detect Stockfish binary path.

    Checks known install paths, then falls back to PATH lookup.

    Returns:
        Path to Stockfish binary.

    Raises:
        FileNotFoundError: If Stockfish is not found anywhere.
    """
    for path_str in _STOCKFISH_PATHS:
        if Path(path_str).is_file():
            return path_str

    which_result = shutil.which("stockfish")
    if which_result is not None:
        return which_result

    raise FileNotFoundError(
        "Stockfish not found. Run scripts/install.sh first."
    )


def _classify_move(cp_loss: int) -> tuple[str, bool]:
    """Classify a move based on centipawn loss.

    Args:
        cp_loss: Absolute centipawn loss (non-negative).

    Returns:
        Tuple of (classification string, is_best boolean).
    """
    abs_loss = abs(cp_loss)
    if abs_loss == 0:
        return "best", True
    for threshold, label in _CLASSIFICATION_THRESHOLDS:
        if abs_loss <= threshold:
            return label, False
    return "blunder", False


class ChessEngine:
    """Stockfish wrapper with adaptive difficulty and analysis."""

    def __init__(self, stockfish_path: str | None = None) -> None:
        """Initialize engine with Stockfish.

        Args:
            stockfish_path: Explicit path to Stockfish binary.
                If None, auto-detects from known locations.

        Raises:
            FileNotFoundError: If Stockfish is not found.
        """
        self._stockfish_path = stockfish_path or _find_stockfish()
        self._engine = chess.engine.SimpleEngine.popen_uci(self._stockfish_path)
        self._target_elo: int = 800
        self._random_pct: float = 0.0
        self._depth: int = 1
        self._use_uci_elo: bool = False
        self.set_difficulty(self._target_elo)

    def _open_engine(self) -> chess.engine.SimpleEngine:
        """Open a fresh Stockfish process.

        Returns:
            New SimpleEngine instance.
        """
        return chess.engine.SimpleEngine.popen_uci(self._stockfish_path)

    def _ensure_engine(self) -> None:
        """Ensure engine process is alive, restart once if terminated."""
        try:
            self._engine.ping()
        except chess.engine.EngineTerminatedError:
            self._engine = self._open_engine()
            self.set_difficulty(self._target_elo)

    def new_game(
        self,
        target_elo: int = 800,
        player_color: str = "white",
        starting_fen: str | None = None,
    ) -> chess.Board:
        """Start a new game with configured difficulty.

        Args:
            target_elo: Target engine strength (default 800).
            player_color: "white" or "black".
            starting_fen: Optional FEN to start from.

        Returns:
            A new chess.Board for the game.
        """
        self.set_difficulty(target_elo)
        if starting_fen is not None:
            return chess.Board(starting_fen)
        return chess.Board()

    def set_difficulty(self, target_elo: int) -> None:
        """Configure engine strength.

        For sub-1320 Elo: uses depth limiting + random move blending.
        For 1320+ Elo: uses Stockfish UCI_Elo directly.

        Args:
            target_elo: Desired engine Elo rating.
        """
        self._target_elo = target_elo

        if target_elo >= 1320:
            self._use_uci_elo = True
            self._random_pct = 0.0
            self._depth = 20
            self._ensure_engine()
            self._engine.configure({"UCI_LimitStrength": True, "UCI_Elo": target_elo})
        else:
            self._use_uci_elo = False
            self._random_pct = max(0.0, 0.85 - (target_elo / 1320) * 0.85)
            self._depth = max(1, min(5, target_elo // 250))
            self._ensure_engine()
            self._engine.configure({"UCI_LimitStrength": False})

    def get_engine_move(self, board: chess.Board) -> chess.Move:
        """Get an engine move at the configured difficulty.

        For sub-1320: randomly picks a legal move with probability
        random_pct, otherwise uses depth-limited search.
        For 1320+: uses UCI_Elo with time-limited search.

        Args:
            board: Current board position.

        Returns:
            The engine's chosen move.

        Raises:
            ValueError: If the game is already over.
        """
        if board.is_game_over():
            raise ValueError("Game is already over")

        self._ensure_engine()

        try:
            return self._get_engine_move_inner(board)
        except chess.engine.EngineTerminatedError:
            self._engine = self._open_engine()
            self.set_difficulty(self._target_elo)
            return self._get_engine_move_inner(board)

    def _get_engine_move_inner(self, board: chess.Board) -> chess.Move:
        """Internal move generation without crash recovery.

        Args:
            board: Current board position.

        Returns:
            The engine's chosen move.
        """
        if self._use_uci_elo:
            result = self._engine.play(board, chess.engine.Limit(time=1.0))
            return result.move

        # Sub-1320: random blend
        if random.random() < self._random_pct:
            legal_moves = list(board.legal_moves)
            return random.choice(legal_moves)

        result = self._engine.play(board, chess.engine.Limit(depth=self._depth))
        return result.move

    def analyze_position(
        self,
        board: chess.Board,
        depth: int = 20,
        multipv: int = 3,
    ) -> list[dict]:
        """Full-strength position analysis regardless of difficulty setting.

        Args:
            board: Position to analyze.
            depth: Analysis depth (default 20).
            multipv: Number of principal variations (default 3).

        Returns:
            List of dicts, each with keys: score_cp, mate, pv (list of SAN moves).
        """
        self._ensure_engine()

        try:
            return self._analyze_position_inner(board, depth, multipv)
        except chess.engine.EngineTerminatedError:
            self._engine = self._open_engine()
            self.set_difficulty(self._target_elo)
            return self._analyze_position_inner(board, depth, multipv)

    def _analyze_position_inner(
        self,
        board: chess.Board,
        depth: int,
        multipv: int,
    ) -> list[dict]:
        """Internal analysis without crash recovery.

        Args:
            board: Position to analyze.
            depth: Analysis depth.
            multipv: Number of principal variations.

        Returns:
            List of analysis dicts.
        """
        infos = self._engine.analyse(
            board,
            chess.engine.Limit(depth=depth),
            multipv=multipv,
        )

        results: list[dict] = []
        for info in infos:
            score = info["score"].relative
            cp = score.score(mate_score=_MATE_SCORE)
            mate = score.mate()

            pv_moves = info.get("pv", [])
            # Convert PV moves to SAN notation
            san_moves: list[str] = []
            temp_board = board.copy()
            for move in pv_moves:
                san_moves.append(temp_board.san(move))
                temp_board.push(move)

            results.append({
                "score_cp": cp,
                "mate": mate,
                "pv": san_moves,
            })

        return results

    def evaluate_move(
        self,
        board: chess.Board,
        move: chess.Move,
    ) -> MoveEvaluation:
        """Evaluate a player's move against the engine's best.

        Analyzes the position before the move (to find best move and score),
        then analyzes after the move to compute centipawn loss.

        Args:
            board: Position before the move is played.
            move: The player's move to evaluate.

        Returns:
            MoveEvaluation dataclass with classification.
        """
        self._ensure_engine()

        try:
            return self._evaluate_move_inner(board, move)
        except chess.engine.EngineTerminatedError:
            self._engine = self._open_engine()
            self.set_difficulty(self._target_elo)
            return self._evaluate_move_inner(board, move)

    def _evaluate_move_inner(
        self,
        board: chess.Board,
        move: chess.Move,
    ) -> MoveEvaluation:
        """Internal move evaluation without crash recovery.

        Args:
            board: Position before the move.
            move: The move to evaluate.

        Returns:
            MoveEvaluation dataclass.
        """
        # Analyze position before move (full strength)
        info_before = self._engine.analyse(
            board,
            chess.engine.Limit(depth=20),
            multipv=1,
        )

        score_before_pov = info_before[0]["score"].relative
        eval_before_cp = score_before_pov.score(mate_score=_MATE_SCORE)

        best_move = info_before[0]["pv"][0]
        best_move_san = board.san(best_move)

        # Get best line in SAN
        pv_moves = info_before[0].get("pv", [])
        best_line_san: list[str] = []
        temp_board = board.copy()
        for pv_move in pv_moves:
            best_line_san.append(temp_board.san(pv_move))
            temp_board.push(pv_move)

        # Player's move in SAN (before pushing)
        move_san = board.san(move)

        # Push the player's move
        board_after = board.copy()
        board_after.push(move)

        # Analyze position after the move
        info_after = self._engine.analyse(
            board_after,
            chess.engine.Limit(depth=20),
            multipv=1,
        )

        # Score after is from opponent's perspective, negate to compare
        score_after_pov = info_after[0]["score"].relative
        eval_after_cp = score_after_pov.score(mate_score=_MATE_SCORE)

        # cp_loss: how much worse the position got for the moving side
        # eval_before is from moving side's view, eval_after is from opponent's view
        # So the moving side's eval after = -eval_after_cp
        cp_loss = eval_before_cp - (-eval_after_cp)
        cp_loss = max(0, cp_loss)

        classification, is_best = _classify_move(cp_loss)

        return MoveEvaluation(
            move_san=move_san,
            best_move_san=best_move_san,
            cp_loss=cp_loss,
            eval_before=eval_before_cp / 100.0,
            eval_after=-eval_after_cp / 100.0,
            classification=classification,
            is_best=is_best,
            best_line=best_line_san,
            tactical_motif=None,
        )

    def close(self) -> None:
        """Clean up Stockfish process."""
        try:
            self._engine.quit()
        except chess.engine.EngineTerminatedError:
            pass


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------


def _cli_analyze(fen: str) -> None:
    """Analyze a FEN position and print top 3 lines.

    Args:
        fen: FEN string of the position to analyze.
    """
    engine = ChessEngine()
    try:
        board = chess.Board(fen)
        results = engine.analyze_position(board, depth=20, multipv=3)

        print(f"Position: {fen}")
        print(f"Side to move: {'White' if board.turn else 'Black'}")
        print()

        for i, line in enumerate(results, 1):
            score_str = (
                f"Mate in {line['mate']}"
                if line["mate"] is not None
                else f"{line['score_cp'] / 100.0:+.2f}"
            )
            pv_str = " ".join(line["pv"][:6])
            print(f"  Line {i}: {score_str}  {pv_str}")
    finally:
        engine.close()


def _cli_play(elo: int, interactive: bool) -> None:
    """Play demo against the engine.

    Args:
        elo: Target engine Elo.
        interactive: If True, run full interactive game loop.
    """
    engine = ChessEngine()
    try:
        board = engine.new_game(target_elo=elo)
        print(f"New game at Elo {elo}")
        print(board)
        print()

        if not interactive:
            # One-move demo: engine plays white's first move
            move = engine.get_engine_move(board)
            san = board.san(move)
            board.push(move)
            print(f"Engine plays: {san}")
            print(board)
            return

        # Interactive game loop - player is white, engine is black
        while not board.is_game_over():
            if board.turn == chess.WHITE:
                print("Your move (SAN or UCI, 'q' to quit): ", end="")
                user_input = input().strip()
                if user_input.lower() == "q":
                    print("Game ended by user.")
                    return

                try:
                    # Try SAN first
                    try:
                        move = board.parse_san(user_input)
                    except chess.InvalidMoveError:
                        move = chess.Move.from_uci(user_input)

                    if move not in board.legal_moves:
                        print("Illegal move. Try again.")
                        continue

                    evaluation = engine.evaluate_move(board, move)
                    board.push(move)

                    print(f"You played: {evaluation.move_san}")
                    print(
                        f"  Classification: {evaluation.classification} "
                        f"(cp_loss: {evaluation.cp_loss})"
                    )
                    if not evaluation.is_best:
                        print(f"  Best was: {evaluation.best_move_san}")
                    print()

                except (chess.InvalidMoveError, chess.IllegalMoveError):
                    print("Invalid move format. Use SAN (e.g., e4) or UCI (e.g., e2e4).")
                    continue
            else:
                move = engine.get_engine_move(board)
                san = board.san(move)
                board.push(move)
                print(f"Engine plays: {san}")

            print(board)
            print()

        print(f"Game over: {board.result()}")
        outcome = board.outcome()
        if outcome is not None and outcome.winner is not None:
            winner = "White" if outcome.winner else "Black"
            print(f"Winner: {winner}")
        else:
            print("Draw")
    finally:
        engine.close()


def main() -> None:
    """CLI entry point for engine.py."""
    parser = argparse.ArgumentParser(
        description="Chess engine wrapper - analyze positions or play demos"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # analyze subcommand
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a FEN position")
    analyze_parser.add_argument("fen", type=str, help="FEN string to analyze")

    # play subcommand
    play_parser = subparsers.add_parser("play", help="Play against the engine")
    play_parser.add_argument(
        "elo", type=int, help="Target engine Elo rating"
    )
    play_parser.add_argument(
        "--interactive", action="store_true", help="Full interactive game loop"
    )

    args = parser.parse_args()

    if args.command == "analyze":
        _cli_analyze(args.fen)
    elif args.command == "play":
        _cli_play(args.elo, args.interactive)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
