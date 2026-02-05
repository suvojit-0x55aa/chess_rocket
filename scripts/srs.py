"""Spaced Repetition System (SRS) manager for Chess Speedrun.

Uses the SM-2 algorithm to schedule review of chess mistakes.
Cards track positions where the player deviated from best play,
enabling targeted practice of weak areas.

CLI interface outputs JSON to stdout for MCP server integration.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# SM-2 interval progression in hours
_INTERVAL_HOURS = [4, 24, 72, 168, 336, 720]

_MIN_EASE_FACTOR = 1.3


class SRSManager:
    """Manages spaced repetition cards with SM-2 scheduling."""

    def __init__(self, cards_path: str = "data/srs_cards.json") -> None:
        """Load cards from JSON file.

        If the file is corrupted, backs it up as .bak and starts fresh.

        Args:
            cards_path: Path to the JSON file storing cards.
        """
        self._cards_path = Path(cards_path)
        self._cards: list[dict] = self._load_cards()

    def _load_cards(self) -> list[dict]:
        """Load cards from disk, handling corruption gracefully.

        Returns:
            List of card dicts. Empty list if file missing or corrupt.
        """
        if not self._cards_path.exists():
            return []

        try:
            text = self._cards_path.read_text(encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, list):
                raise ValueError("Cards file must contain a JSON array")
            return data
        except (json.JSONDecodeError, ValueError):
            # Backup corrupted file and start fresh
            backup_path = self._cards_path.with_suffix(".bak")
            shutil.copy2(self._cards_path, backup_path)
            return []

    def _save(self) -> None:
        """Save cards to JSON file with atomic write."""
        self._cards_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._cards_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self._cards, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, self._cards_path)

    def add_card(
        self,
        fen: str,
        player_move: str,
        best_move: str,
        cp_loss: int,
        classification: str,
        motif: str | None = None,
        explanation: str = "",
    ) -> dict:
        """Add a new SRS card for a mistake position.

        Args:
            fen: Board position FEN where the mistake occurred.
            player_move: The move the player actually made (SAN).
            best_move: The engine's best move (SAN).
            cp_loss: Centipawn loss from the player's move.
            classification: Move classification (inaccuracy/mistake/blunder).
            motif: Optional tactical motif tag.
            explanation: Optional text explaining why best_move is better.

        Returns:
            The newly created card dict.
        """
        now = datetime.now(timezone.utc)
        card: dict = {
            "id": str(uuid.uuid4()),
            "fen": fen,
            "player_move": player_move,
            "best_move": best_move,
            "cp_loss": cp_loss,
            "classification": classification,
            "motif": motif,
            "explanation": explanation,
            "created_at": now.isoformat(),
            "next_review": (now + timedelta(hours=_INTERVAL_HOURS[0])).isoformat(),
            "interval_hours": _INTERVAL_HOURS[0],
            "ease_factor": 2.5,
            "repetitions": 0,
            "quality_history": [],
        }
        self._cards.append(card)
        self._save()
        return card

    def get_due_cards(self) -> list[dict]:
        """Return all cards whose next_review is at or before now.

        Returns:
            List of due card dicts, sorted by next_review ascending.
        """
        now = datetime.now(timezone.utc)
        due: list[dict] = []
        for card in self._cards:
            review_time = datetime.fromisoformat(card["next_review"])
            if review_time <= now:
                due.append(card)
        due.sort(key=lambda c: c["next_review"])
        return due

    def review_card(self, card_id: str, quality: int) -> dict:
        """Review a card with the given quality score.

        Applies the SM-2 algorithm to update the card's scheduling.

        Args:
            card_id: UUID of the card to review.
            quality: Review quality score (0-5).

        Returns:
            The updated card dict.

        Raises:
            ValueError: If card_id is not found or quality is out of range.
        """
        if not isinstance(quality, int) or quality < 0 or quality > 5:
            raise ValueError(
                f"Quality must be an integer between 0 and 5, got {quality}"
            )

        card = self._find_card(card_id)
        updated = self._sm2_update(card, quality)

        # Replace card in list (immutable-style: build new list)
        self._cards = [
            updated if c["id"] == card_id else c for c in self._cards
        ]
        self._save()
        return updated

    def get_stats(self) -> dict:
        """Return summary statistics about the card collection.

        Returns:
            Dict with keys: total, due, avg_ease, by_classification.
        """
        now = datetime.now(timezone.utc)
        due_count = 0
        ease_sum = 0.0
        by_classification: dict[str, int] = {}

        for card in self._cards:
            review_time = datetime.fromisoformat(card["next_review"])
            if review_time <= now:
                due_count += 1
            ease_sum += card["ease_factor"]
            cls = card["classification"]
            by_classification[cls] = by_classification.get(cls, 0) + 1

        total = len(self._cards)
        return {
            "total": total,
            "due": due_count,
            "avg_ease": round(ease_sum / total, 3) if total > 0 else 0.0,
            "by_classification": by_classification,
        }

    def _find_card(self, card_id: str) -> dict:
        """Find a card by ID.

        Args:
            card_id: UUID string to search for.

        Returns:
            The matching card dict.

        Raises:
            ValueError: If no card with that ID exists.
        """
        for card in self._cards:
            if card["id"] == card_id:
                return card
        raise ValueError(f"Card not found: {card_id}")

    def _sm2_update(self, card: dict, quality: int) -> dict:
        """Apply SM-2 algorithm to compute new scheduling for a card.

        Args:
            card: The card dict to update.
            quality: Review quality score (0-5).

        Returns:
            A new card dict with updated scheduling fields.
        """
        now = datetime.now(timezone.utc)

        # Copy card to avoid mutation
        updated = {**card}

        # Record quality in history
        updated["quality_history"] = [*card["quality_history"], quality]

        # Update ease factor using SM-2 formula
        ef = card["ease_factor"]
        ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        ef = max(_MIN_EASE_FACTOR, ef)
        updated["ease_factor"] = round(ef, 4)

        if quality < 3:
            # Failed: reset to first interval
            updated["interval_hours"] = _INTERVAL_HOURS[0]
            updated["repetitions"] = 0
        else:
            # Passed: advance to next interval
            reps = card["repetitions"]
            if reps < len(_INTERVAL_HOURS):
                new_interval = _INTERVAL_HOURS[reps]
            else:
                # Beyond the fixed sequence: multiply by ease factor
                prev_interval = card["interval_hours"]
                new_interval = round(prev_interval * ef)
            updated["interval_hours"] = new_interval
            updated["repetitions"] = reps + 1

        updated["next_review"] = (
            now + timedelta(hours=updated["interval_hours"])
        ).isoformat()

        return updated


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------


def _cli_due(manager: SRSManager) -> None:
    """Print due cards as JSON to stdout."""
    due = manager.get_due_cards()
    print(json.dumps(due, indent=2, ensure_ascii=False))


def _cli_review(manager: SRSManager, card_id: str, quality: int) -> None:
    """Review a card and print updated card as JSON."""
    updated = manager.review_card(card_id, quality)
    print(json.dumps(updated, indent=2, ensure_ascii=False))


def _cli_add(
    manager: SRSManager,
    fen: str,
    player_move: str,
    best_move: str,
    cp_loss: int,
    classification: str,
    motif: str | None,
    explanation: str,
) -> None:
    """Add a card and print it as JSON."""
    card = manager.add_card(
        fen=fen,
        player_move=player_move,
        best_move=best_move,
        cp_loss=cp_loss,
        classification=classification,
        motif=motif,
        explanation=explanation,
    )
    print(json.dumps(card, indent=2, ensure_ascii=False))


def _cli_stats(manager: SRSManager) -> None:
    """Print stats as JSON to stdout."""
    stats = manager.get_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))


def main() -> None:
    """CLI entry point for srs.py."""
    parser = argparse.ArgumentParser(
        description="SRS card manager - spaced repetition for chess mistakes"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # due subcommand
    subparsers.add_parser("due", help="List due cards")

    # review subcommand
    review_parser = subparsers.add_parser("review", help="Review a card")
    review_parser.add_argument("card_id", type=str, help="Card UUID")
    review_parser.add_argument("quality", type=int, help="Quality score 0-5")

    # add subcommand
    add_parser = subparsers.add_parser("add", help="Add a new card")
    add_parser.add_argument("--fen", type=str, required=True, help="Board FEN")
    add_parser.add_argument(
        "--player-move", type=str, required=True, help="Player's move (SAN)"
    )
    add_parser.add_argument(
        "--best-move", type=str, required=True, help="Best move (SAN)"
    )
    add_parser.add_argument(
        "--cp-loss", type=int, required=True, help="Centipawn loss"
    )
    add_parser.add_argument(
        "--classification",
        type=str,
        required=True,
        help="Move classification (inaccuracy/mistake/blunder)",
    )
    add_parser.add_argument(
        "--motif", type=str, default=None, help="Tactical motif"
    )
    add_parser.add_argument(
        "--explanation", type=str, default="", help="Why best move is better"
    )

    # stats subcommand
    subparsers.add_parser("stats", help="Show card statistics")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    manager = SRSManager()

    if args.command == "due":
        _cli_due(manager)
    elif args.command == "review":
        _cli_review(manager, args.card_id, args.quality)
    elif args.command == "add":
        _cli_add(
            manager,
            fen=args.fen,
            player_move=args.player_move,
            best_move=args.best_move,
            cp_loss=args.cp_loss,
            classification=args.classification,
            motif=args.motif,
            explanation=args.explanation,
        )
    elif args.command == "stats":
        _cli_stats(manager)


if __name__ == "__main__":
    main()
