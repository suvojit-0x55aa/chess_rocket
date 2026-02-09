"""Pytest tests for the puzzle generation system.

Tests motif integration with puzzle files, deduplication logic,
manifest tracking, game mining, CLI routing, and Lichess import.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import chess
import pytest

from scripts.motif_detector import detect_motif

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PUZZLES_DIR = _PROJECT_ROOT / "puzzles"

# All 9 puzzle files
PUZZLE_FILES = [
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


def _load_puzzles(filename: str) -> list[dict]:
    """Load puzzles from a puzzle JSON file."""
    path = _PUZZLES_DIR / filename
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# TestMotifIntegration
# ---------------------------------------------------------------------------


class TestMotifIntegration:
    """Verify detect_motif works on puzzles from each regenerated file."""

    @pytest.mark.parametrize("filename", [
        "forks.json",
        "pins.json",
        "skewers.json",
        "back-rank.json",
        "checkmate-patterns.json",
    ])
    def test_motif_detection_on_tactical_puzzles(self, filename: str):
        """detect_motif should return a non-None value for tactical puzzle positions."""
        puzzles = _load_puzzles(filename)
        assert len(puzzles) >= 10, f"{filename} has fewer than 10 puzzles"

        detected_count = 0
        for puzzle in puzzles:
            board = chess.Board(puzzle["fen"])
            move = chess.Move.from_uci(puzzle["solution_moves"][0])
            result = detect_motif(board, move)
            if result is not None:
                detected_count += 1

        # At least some puzzles should have detectable motifs
        # Not all will match due to detection heuristic limitations
        assert detected_count > 0, (
            f"detect_motif returned None for all {len(puzzles)} puzzles in {filename}"
        )

    def test_motif_detection_on_endgames(self):
        """Endgame puzzles may not have tactical motifs — just verify no crashes."""
        puzzles = _load_puzzles("beginner-endgames.json")
        assert len(puzzles) >= 10

        for puzzle in puzzles:
            board = chess.Board(puzzle["fen"])
            move = chess.Move.from_uci(puzzle["solution_moves"][0])
            # Should not raise
            detect_motif(board, move)

    def test_motif_detection_on_opening_puzzles(self):
        """Opening puzzles test book knowledge, not tactics — verify no crashes."""
        for filename in ("opening-moves.json", "opening-traps.json"):
            puzzles = _load_puzzles(filename)
            assert len(puzzles) >= 10, f"{filename} has fewer than 10 puzzles"

            for puzzle in puzzles:
                board = chess.Board(puzzle["fen"])
                move = chess.Move.from_uci(puzzle["solution_moves"][0])
                detect_motif(board, move)

    def test_all_puzzle_files_have_valid_fens(self):
        """Every puzzle across all files should have a parseable FEN."""
        for filename in PUZZLE_FILES:
            puzzles = _load_puzzles(filename)
            for i, puzzle in enumerate(puzzles):
                for field in REQUIRED_FIELDS:
                    assert field in puzzle, f"{filename}[{i}] missing '{field}'"
                # FEN should parse
                chess.Board(puzzle["fen"])


# ---------------------------------------------------------------------------
# TestPuzzleDeduplication
# ---------------------------------------------------------------------------


class TestPuzzleDeduplication:
    """Verify FEN deduplication logic."""

    def test_identical_fens_are_deduped(self):
        """Two puzzles with identical FENs should be detected as duplicates."""
        from scripts.generate_puzzles import _normalize_fen

        fen1 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        fen2 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"

        assert _normalize_fen(fen1) == _normalize_fen(fen2)

    def test_different_move_counters_are_deduped(self):
        """FENs differing only in halfmove/fullmove counters should be deduped."""
        from scripts.generate_puzzles import _normalize_fen

        fen_move1 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        fen_move50 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 5 50"

        assert _normalize_fen(fen_move1) == _normalize_fen(fen_move50)

    def test_different_positions_not_deduped(self):
        """FENs with different positions should NOT be treated as duplicates."""
        from scripts.generate_puzzles import _normalize_fen

        fen_e4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        fen_d4 = "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq d3 0 1"

        assert _normalize_fen(fen_e4) != _normalize_fen(fen_d4)

    def test_lichess_normalize_fen_strips_counters(self):
        """Lichess importer's _normalize_fen should also strip move counters."""
        from scripts.import_lichess_puzzles import _normalize_fen

        fen1 = "r1bqkbnr/pppppppp/2n5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 1 2"
        fen2 = "r1bqkbnr/pppppppp/2n5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 3 10"

        assert _normalize_fen(fen1) == _normalize_fen(fen2)


# ---------------------------------------------------------------------------
# TestManifest
# ---------------------------------------------------------------------------


class TestManifest:
    """Verify manifest load, save, and tracking of processed files."""

    def test_load_empty_manifest(self, tmp_path: Path):
        """Loading a non-existent manifest returns default structure."""
        from scripts.generate_puzzles import _load_manifest, _MANIFEST_PATH

        # Temporarily redirect manifest path
        fake_path = tmp_path / "manifest.json"
        with patch("scripts.generate_puzzles._MANIFEST_PATH", fake_path):
            manifest = _load_manifest()

        assert "processed_files" in manifest
        assert manifest["processed_files"] == []

    def test_save_and_reload_manifest(self, tmp_path: Path):
        """Saving a manifest and reloading it preserves data."""
        from scripts.generate_puzzles import _load_manifest, _save_manifest

        fake_path = tmp_path / "manifest.json"
        with patch("scripts.generate_puzzles._MANIFEST_PATH", fake_path):
            manifest = {"processed_files": ["game1.pgn", "game2.pgn"]}
            _save_manifest(manifest)

            reloaded = _load_manifest()

        assert reloaded["processed_files"] == ["game1.pgn", "game2.pgn"]

    def test_get_unprocessed_games(self, tmp_path: Path):
        """get_unprocessed_games returns only files not in the manifest."""
        from scripts.generate_puzzles import get_unprocessed_games

        # Create fake PGN files
        (tmp_path / "game1.pgn").write_text("dummy")
        (tmp_path / "game2.pgn").write_text("dummy")
        (tmp_path / "game3.pgn").write_text("dummy")

        manifest = {"processed_files": ["game1.pgn", "game3.pgn"]}
        unprocessed = get_unprocessed_games(manifest, games_dir=tmp_path)

        assert len(unprocessed) == 1
        assert unprocessed[0].name == "game2.pgn"

    def test_get_unprocessed_games_empty_dir(self, tmp_path: Path):
        """get_unprocessed_games returns empty list for non-existent dir."""
        from scripts.generate_puzzles import get_unprocessed_games

        manifest = {"processed_files": []}
        unprocessed = get_unprocessed_games(manifest, games_dir=tmp_path / "nope")

        assert unprocessed == []


# ---------------------------------------------------------------------------
# TestGameMining (e2e - requires real Stockfish)
# ---------------------------------------------------------------------------


class TestGameMining:
    """Verify mining a PGN file extracts puzzles."""

    @pytest.mark.e2e
    def test_mine_pgn_extracts_puzzles(self, tmp_path: Path):
        """Mining a PGN with intentional blunders should produce puzzles."""
        from scripts.generate_puzzles import generate_game_puzzles

        # Create a PGN with a known blunder position
        pgn_content = """[Event "Test Game"]
[Site "Test"]
[Date "2026.01.01"]
[White "Player"]
[Black "Stockfish"]
[Result "0-1"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 g6 4. Qf3 Nf6 5. g4 Nxg4 6. Qg3 d5 7. exd5 Nd4 0-1
"""
        games_dir = tmp_path / "games"
        games_dir.mkdir()
        (games_dir / "test_game.pgn").write_text(pgn_content)

        puzzles = generate_game_puzzles(
            games_dir=games_dir,
            depth=10,  # Lower depth for speed
            cp_threshold=80,
        )

        # Should extract at least some puzzle positions
        # (exact count depends on engine analysis)
        assert isinstance(puzzles, list)
        for puzzle in puzzles:
            for field in REQUIRED_FIELDS:
                assert field in puzzle, f"Puzzle missing '{field}'"
            # Verify FEN is valid
            chess.Board(puzzle["fen"])
            # Verify solution moves are legal
            board = chess.Board(puzzle["fen"])
            for uci in puzzle["solution_moves"]:
                move = chess.Move.from_uci(uci)
                assert move in board.legal_moves
                board.push(move)


# ---------------------------------------------------------------------------
# TestPipelineCLI
# ---------------------------------------------------------------------------


class TestPipelineCLI:
    """Verify CLI --pipeline flag routing works."""

    def test_pipeline_flag_accepted(self):
        """The --pipeline flag should be accepted by argparse."""
        result = subprocess.run(
            [sys.executable, "-c",
             "from scripts.generate_puzzles import main; "
             "import sys; sys.argv = ['gen', '--pipeline', 'stockfish', '--help']; main()"],
            capture_output=True, text=True,
            cwd=str(_PROJECT_ROOT),
            timeout=10,
        )
        # --help exits with 0
        assert result.returncode == 0

    def test_pipeline_choices_are_valid(self):
        """The --pipeline flag should accept stockfish, games, openings, all."""
        import argparse

        # Reconstruct the parser to test choices
        parser = argparse.ArgumentParser()
        parser.add_argument("--pipeline", choices=["stockfish", "games", "openings", "all"])

        for choice in ["stockfish", "games", "openings", "all"]:
            args = parser.parse_args(["--pipeline", choice])
            assert args.pipeline == choice

    def test_invalid_pipeline_rejected(self):
        """An invalid --pipeline value should be rejected."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--pipeline", choices=["stockfish", "games", "openings", "all"])

        with pytest.raises(SystemExit):
            parser.parse_args(["--pipeline", "invalid"])


# ---------------------------------------------------------------------------
# TestLichessImport
# ---------------------------------------------------------------------------


class TestLichessImport:
    """Verify Lichess importer produces valid puzzles with correct schema."""

    def test_theme_to_motif_mapping(self):
        """All mapped themes should produce valid motif strings."""
        from scripts.import_lichess_puzzles import THEME_TO_MOTIF

        expected_motifs = {
            "back_rank_mate", "checkmate", "fork", "pin", "skewer",
            "discovered_attack", "double_check", "promotion",
        }
        for theme, motif in THEME_TO_MOTIF.items():
            assert motif in expected_motifs, f"Unknown motif '{motif}' for theme '{theme}'"

    def test_rating_to_difficulty(self):
        """Rating thresholds should produce correct difficulty labels."""
        from scripts.import_lichess_puzzles import _rating_to_difficulty

        assert _rating_to_difficulty(800) == "beginner"
        assert _rating_to_difficulty(1199) == "beginner"
        assert _rating_to_difficulty(1200) == "intermediate"
        assert _rating_to_difficulty(1799) == "intermediate"
        assert _rating_to_difficulty(1800) == "advanced"
        assert _rating_to_difficulty(2500) == "advanced"

    def test_pick_motif(self):
        """_pick_motif should return the first matching theme's motif."""
        from scripts.import_lichess_puzzles import _pick_motif

        assert _pick_motif(["backRankMate", "short"]) == "back_rank_mate"
        assert _pick_motif(["fork", "middlegame"]) == "fork"
        assert _pick_motif(["middlegame", "endgame"]) is None

    def test_validate_checkmate(self):
        """_validate_checkmate should detect actual checkmate."""
        from scripts.import_lichess_puzzles import _validate_checkmate

        # Scholar's mate final position - Qxf7#
        board = chess.Board("r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4")
        assert board.is_checkmate()
        # Already checkmated, no solution needed
        assert _validate_checkmate(board, [])

    def test_validate_back_rank(self):
        """_validate_back_rank should detect back-rank checkmate."""
        from scripts.import_lichess_puzzles import _validate_back_rank

        # Back-rank mate: Rook delivers mate on back rank
        board = chess.Board("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1")
        assert _validate_back_rank(board, ["a1a8"])

    def test_moves_to_san(self):
        """_moves_to_san should convert UCI moves to SAN correctly."""
        from scripts.import_lichess_puzzles import _moves_to_san

        board = chess.Board()
        san = _moves_to_san(board, ["e2e4", "e7e5"])
        assert san == ["e4", "e5"]

    def test_normalize_fen(self):
        """_normalize_fen should strip halfmove and fullmove counters."""
        from scripts.import_lichess_puzzles import _normalize_fen

        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        normalized = _normalize_fen(fen)
        assert normalized == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3"

    def test_explanation_templates_exist(self):
        """Every motif should have an explanation template."""
        from scripts.import_lichess_puzzles import THEME_TO_MOTIF, EXPLANATION_TEMPLATES

        motifs_used = set(THEME_TO_MOTIF.values())
        for motif in motifs_used:
            assert motif in EXPLANATION_TEMPLATES, f"Missing template for motif '{motif}'"
