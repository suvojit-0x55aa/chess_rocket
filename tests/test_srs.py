"""Pytest tests for SRSManager class.

Tests cover SM-2 algorithm, card lifecycle, due filtering,
error handling, and corrupted file recovery.
All tests use tmp_path for isolation from real data.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from scripts.srs import SRSManager, _INTERVAL_HOURS, _MIN_EASE_FACTOR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def _make_manager(tmp_path) -> SRSManager:
    """Create an SRSManager using a temporary directory."""
    cards_file = tmp_path / "srs_cards.json"
    cards_file.write_text("[]", encoding="utf-8")
    return SRSManager(cards_path=str(cards_file))


def _add_sample_card(manager: SRSManager) -> dict:
    """Add a sample card and return it."""
    return manager.add_card(
        fen=_SAMPLE_FEN,
        player_move="e5",
        best_move="d5",
        cp_loss=45,
        classification="inaccuracy",
        motif=None,
        explanation="d5 controls the center more effectively",
    )


# ---------------------------------------------------------------------------
# SM-2 interval progression
# ---------------------------------------------------------------------------


class TestSM2IntervalProgression:

    def test_sm2_interval_progression(self, tmp_path):
        """Quality 4 repeatedly: 4h -> 24h -> 72h -> 168h -> 336h -> 720h -> 720*EF."""
        manager = _make_manager(tmp_path)
        card = _add_sample_card(manager)
        card_id = card["id"]

        # Walk through the fixed interval sequence
        expected_intervals = list(_INTERVAL_HOURS)  # [4, 24, 72, 168, 336, 720]

        for i, expected_hours in enumerate(expected_intervals):
            # Patch time so card is always due
            with patch("scripts.srs.datetime") as mock_dt:
                mock_now = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i * 60)
                mock_dt.now.return_value = mock_now
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                card = manager.review_card(card_id, quality=4)

            assert card["interval_hours"] == expected_hours, (
                f"Rep {i}: expected {expected_hours}h, got {card['interval_hours']}h"
            )

        # One more review beyond the fixed sequence: should multiply by ease
        with patch("scripts.srs.datetime") as mock_dt:
            mock_now = datetime(2024, 6, 1, tzinfo=timezone.utc)
            mock_dt.now.return_value = mock_now
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            card = manager.review_card(card_id, quality=4)

        expected_beyond = round(720 * card["ease_factor"])
        assert card["interval_hours"] == expected_beyond


class TestFailedCardResets:

    def test_failed_card_resets(self, tmp_path):
        """Quality 2 (fail) resets interval to 4h and repetitions to 0."""
        manager = _make_manager(tmp_path)
        card = _add_sample_card(manager)
        card_id = card["id"]

        # Pass a few times first to advance
        for _ in range(3):
            with patch("scripts.srs.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2024, 6, 1, tzinfo=timezone.utc)
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                card = manager.review_card(card_id, quality=4)

        assert card["repetitions"] == 3
        assert card["interval_hours"] == _INTERVAL_HOURS[2]  # 72h

        # Now fail
        with patch("scripts.srs.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 7, 1, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            card = manager.review_card(card_id, quality=2)

        assert card["interval_hours"] == _INTERVAL_HOURS[0]  # 4h
        assert card["repetitions"] == 0


class TestEaseFactorMinimum:

    def test_ease_factor_minimum(self, tmp_path):
        """Many quality=0 reviews don't drop ease below 1.3."""
        manager = _make_manager(tmp_path)
        card = _add_sample_card(manager)
        card_id = card["id"]

        for _ in range(20):
            with patch("scripts.srs.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2024, 6, 1, tzinfo=timezone.utc)
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                card = manager.review_card(card_id, quality=0)

        assert card["ease_factor"] >= _MIN_EASE_FACTOR
        assert card["ease_factor"] == _MIN_EASE_FACTOR


class TestEaseFactorCalculation:

    def test_ease_factor_calculation(self, tmp_path):
        """Verify SM-2 ease formula with specific quality values."""
        manager = _make_manager(tmp_path)
        card = _add_sample_card(manager)
        card_id = card["id"]
        initial_ef = card["ease_factor"]  # 2.5

        # Quality 5: EF' = 2.5 + (0.1 - 0*0.08) = 2.6
        with patch("scripts.srs.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 6, 1, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            card = manager.review_card(card_id, quality=5)

        expected_ef = initial_ef + (0.1 - (5 - 5) * (0.08 + (5 - 5) * 0.02))
        assert card["ease_factor"] == round(expected_ef, 4)

        # Quality 3: EF' = 2.6 + (0.1 - 2*(0.08 + 2*0.02)) = 2.6 + (0.1 - 0.24) = 2.46
        prev_ef = card["ease_factor"]
        with patch("scripts.srs.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 6, 2, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            card = manager.review_card(card_id, quality=3)

        expected_ef = prev_ef + (0.1 - (5 - 3) * (0.08 + (5 - 3) * 0.02))
        assert card["ease_factor"] == round(expected_ef, 4)

        # Quality 0: EF' = prev + (0.1 - 5*(0.08 + 5*0.02)) = prev + (0.1 - 0.9) = prev - 0.8
        prev_ef = card["ease_factor"]
        with patch("scripts.srs.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 6, 3, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            card = manager.review_card(card_id, quality=0)

        expected_ef = max(_MIN_EASE_FACTOR, prev_ef + (0.1 - (5 - 0) * (0.08 + (5 - 0) * 0.02)))
        assert card["ease_factor"] == round(expected_ef, 4)


# ---------------------------------------------------------------------------
# Due card filtering
# ---------------------------------------------------------------------------


class TestDueCardFiltering:

    def test_due_card_filtering(self, tmp_path):
        """Cards with next_review in the past are returned; future ones are not."""
        cards_file = tmp_path / "srs_cards.json"
        now = datetime.now(timezone.utc)

        # Manually create cards with controlled next_review times
        past_card = {
            "id": "past-card-id",
            "fen": _SAMPLE_FEN,
            "player_move": "e5",
            "best_move": "d5",
            "cp_loss": 45,
            "classification": "inaccuracy",
            "motif": None,
            "explanation": "",
            "created_at": (now - timedelta(hours=10)).isoformat(),
            "next_review": (now - timedelta(hours=1)).isoformat(),
            "interval_hours": 4,
            "ease_factor": 2.5,
            "repetitions": 0,
            "quality_history": [],
        }
        future_card = {
            "id": "future-card-id",
            "fen": _SAMPLE_FEN,
            "player_move": "Nf6",
            "best_move": "d5",
            "cp_loss": 30,
            "classification": "good",
            "motif": None,
            "explanation": "",
            "created_at": now.isoformat(),
            "next_review": (now + timedelta(hours=10)).isoformat(),
            "interval_hours": 24,
            "ease_factor": 2.5,
            "repetitions": 1,
            "quality_history": [4],
        }

        cards_file.write_text(
            json.dumps([past_card, future_card], indent=2),
            encoding="utf-8",
        )

        manager = SRSManager(cards_path=str(cards_file))
        due = manager.get_due_cards()

        assert len(due) == 1
        assert due[0]["id"] == "past-card-id"


# ---------------------------------------------------------------------------
# Add card
# ---------------------------------------------------------------------------


class TestAddCard:

    def test_add_card(self, tmp_path):
        """Adding a card creates correct structure with all fields."""
        manager = _make_manager(tmp_path)
        card = manager.add_card(
            fen=_SAMPLE_FEN,
            player_move="e5",
            best_move="d5",
            cp_loss=45,
            classification="inaccuracy",
            motif="center_control",
            explanation="d5 controls the center more effectively",
        )

        # Check all required fields exist
        assert "id" in card
        assert len(card["id"]) == 36  # UUID format
        assert card["fen"] == _SAMPLE_FEN
        assert card["player_move"] == "e5"
        assert card["best_move"] == "d5"
        assert card["cp_loss"] == 45
        assert card["classification"] == "inaccuracy"
        assert card["motif"] == "center_control"
        assert card["explanation"] == "d5 controls the center more effectively"
        assert card["interval_hours"] == 4
        assert card["ease_factor"] == 2.5
        assert card["repetitions"] == 0
        assert card["quality_history"] == []

        # Timestamps are valid ISO 8601
        created = datetime.fromisoformat(card["created_at"])
        review = datetime.fromisoformat(card["next_review"])
        assert review > created

        # Card is persisted
        cards_file = tmp_path / "srs_cards.json"
        saved = json.loads(cards_file.read_text(encoding="utf-8"))
        assert len(saved) == 1
        assert saved[0]["id"] == card["id"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestReviewCardNotFound:

    def test_review_card_not_found(self, tmp_path):
        """ValueError raised for unknown card ID."""
        manager = _make_manager(tmp_path)
        with pytest.raises(ValueError, match="Card not found"):
            manager.review_card("nonexistent-uuid", quality=4)


class TestQualityOutOfRange:

    def test_quality_out_of_range(self, tmp_path):
        """ValueError raised for quality < 0 or > 5."""
        manager = _make_manager(tmp_path)
        card = _add_sample_card(manager)

        with pytest.raises(ValueError, match="Quality must be"):
            manager.review_card(card["id"], quality=-1)

        with pytest.raises(ValueError, match="Quality must be"):
            manager.review_card(card["id"], quality=6)

        with pytest.raises(ValueError, match="Quality must be"):
            manager.review_card(card["id"], quality=10)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:

    def test_stats(self, tmp_path):
        """Correct stats returned for a mix of cards."""
        cards_file = tmp_path / "srs_cards.json"
        now = datetime.now(timezone.utc)

        cards = [
            {
                "id": "card-1",
                "fen": _SAMPLE_FEN,
                "player_move": "e5",
                "best_move": "d5",
                "cp_loss": 45,
                "classification": "inaccuracy",
                "motif": None,
                "explanation": "",
                "created_at": now.isoformat(),
                "next_review": (now - timedelta(hours=1)).isoformat(),
                "interval_hours": 4,
                "ease_factor": 2.5,
                "repetitions": 0,
                "quality_history": [],
            },
            {
                "id": "card-2",
                "fen": _SAMPLE_FEN,
                "player_move": "Nf6",
                "best_move": "d5",
                "cp_loss": 200,
                "classification": "mistake",
                "motif": None,
                "explanation": "",
                "created_at": now.isoformat(),
                "next_review": (now + timedelta(hours=10)).isoformat(),
                "interval_hours": 24,
                "ease_factor": 2.3,
                "repetitions": 1,
                "quality_history": [3],
            },
            {
                "id": "card-3",
                "fen": _SAMPLE_FEN,
                "player_move": "h6",
                "best_move": "d5",
                "cp_loss": 350,
                "classification": "blunder",
                "motif": None,
                "explanation": "",
                "created_at": now.isoformat(),
                "next_review": (now - timedelta(hours=2)).isoformat(),
                "interval_hours": 4,
                "ease_factor": 2.0,
                "repetitions": 0,
                "quality_history": [1],
            },
        ]
        cards_file.write_text(json.dumps(cards, indent=2), encoding="utf-8")

        manager = SRSManager(cards_path=str(cards_file))
        stats = manager.get_stats()

        assert stats["total"] == 3
        assert stats["due"] == 2  # card-1 and card-3 are due
        assert stats["avg_ease"] == round((2.5 + 2.3 + 2.0) / 3, 3)
        assert stats["by_classification"] == {
            "inaccuracy": 1,
            "mistake": 1,
            "blunder": 1,
        }

    def test_stats_empty(self, tmp_path):
        """Stats on empty collection return zeros."""
        manager = _make_manager(tmp_path)
        stats = manager.get_stats()

        assert stats["total"] == 0
        assert stats["due"] == 0
        assert stats["avg_ease"] == 0.0
        assert stats["by_classification"] == {}


# ---------------------------------------------------------------------------
# Corrupted JSON
# ---------------------------------------------------------------------------


class TestCorruptedJson:

    def test_corrupted_json(self, tmp_path):
        """Corrupted file gets backed up, manager starts fresh."""
        cards_file = tmp_path / "srs_cards.json"
        cards_file.write_text("{invalid json[[[", encoding="utf-8")

        manager = SRSManager(cards_path=str(cards_file))

        # Should start with empty cards
        assert manager.get_due_cards() == []
        assert manager.get_stats()["total"] == 0

        # Backup should exist
        backup_file = tmp_path / "srs_cards.bak"
        assert backup_file.exists()
        assert backup_file.read_text(encoding="utf-8") == "{invalid json[[["

        # Should be able to add cards normally after recovery
        card = _add_sample_card(manager)
        assert card["id"] is not None
        assert manager.get_stats()["total"] == 1
