#!/usr/bin/env python3
"""Export progress reports and game summaries as markdown."""

import json
import sys
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
PROGRESS_FILE = DATA_DIR / "progress.json"
SESSIONS_DIR = DATA_DIR / "sessions"
GAMES_DIR = DATA_DIR / "games"
SRS_FILE = DATA_DIR / "srs_cards.json"


def _load_json(filepath: Path) -> dict | list | None:
    """Load JSON file, returning None on error."""
    try:
        with open(filepath) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print(f"Warning: Could not read {filepath.name}, skipping.", file=sys.stderr)
        return None


def export_progress() -> str:
    """Export progress report from data/progress.json as markdown."""
    if not PROGRESS_FILE.exists():
        return "No progress data found. Play some games first!"

    progress = _load_json(PROGRESS_FILE)
    if progress is None:
        return "No progress data found. Play some games first!"

    lines = ["# Chess Speedrun Progress Report", ""]

    # Current Level
    lines.append("## Current Level")
    lines.append(f"- Estimated Elo: {progress.get('estimated_elo', progress.get('current_elo', 'Unknown'))}")
    lines.append(f"- Sessions completed: {progress.get('sessions_completed', 0)}")
    lines.append(f"- Current streak: {progress.get('streak', 0)}")
    lines.append(f"- Total games: {progress.get('total_games', 0)}")
    lines.append("")

    # Accuracy Trends
    accuracy = progress.get("accuracy_history", [])
    if accuracy:
        last_five = accuracy[-5:]
        avg = sum(last_five) / len(last_five)
        best = max(accuracy)
        lines.append("## Accuracy Trends")
        lines.append(f"- Last {len(last_five)} games average: {avg:.0f}%")
        lines.append(f"- Best game: {best:.0f}%")
        lines.append("")

    # Areas for Improvement
    areas = progress.get("areas_for_improvement", [])
    if areas:
        lines.append("## Areas for Improvement")
        for area in areas:
            lines.append(f"- {area}")
        lines.append("")

    # SRS Review Status
    if SRS_FILE.exists():
        cards = _load_json(SRS_FILE)
        if isinstance(cards, list):
            now = datetime.now().isoformat()
            due = sum(
                1
                for c in cards
                if isinstance(c, dict) and c.get("next_review", "") <= now
            )
            ease_factors = [
                c.get("ease_factor", 2.5)
                for c in cards
                if isinstance(c, dict) and "ease_factor" in c
            ]
            avg_ease = (
                sum(ease_factors) / len(ease_factors) if ease_factors else 0
            )

            lines.append("## SRS Review Status")
            lines.append(f"- Total cards: {len(cards)}")
            lines.append(f"- Due for review: {due}")
            if ease_factors:
                lines.append(f"- Average ease factor: {avg_ease:.1f}")
            lines.append("")

    return "\n".join(lines)


def export_games() -> str:
    """Export game summaries from data/sessions/ and data/games/ as markdown."""
    game_files = []

    for directory in [SESSIONS_DIR, GAMES_DIR]:
        if directory.exists():
            game_files.extend(sorted(directory.glob("*.json")))

    if not game_files:
        return "No games found."

    lines = ["# Game Summaries", ""]
    game_num = 0

    for filepath in game_files:
        data = _load_json(filepath)
        if data is None:
            continue

        game_num += 1
        date = data.get("date", data.get("created_at", "Unknown"))
        if isinstance(date, str) and len(date) > 10:
            date = date[:10]

        opponent_elo = data.get("target_elo", data.get("opponent_elo", "Unknown"))
        result = data.get("result", "Unknown")
        accuracy = data.get("accuracy", {})

        lines.append(f"## Game {game_num} - {date}")
        lines.append(f"- Opponent Elo: {opponent_elo}")
        lines.append(f"- Result: {result}")

        if isinstance(accuracy, dict):
            white_acc = accuracy.get("white", 0)
            black_acc = accuracy.get("black", 0)
            lines.append(f"- Accuracy: White {white_acc:.0f}% / Black {black_acc:.0f}%")
        elif isinstance(accuracy, (int, float)):
            lines.append(f"- Accuracy: {accuracy:.0f}%")

        mistakes = data.get("mistakes", [])
        if mistakes:
            lines.append("- Key mistakes:")
            for m in mistakes[:5]:
                if isinstance(m, dict):
                    move = m.get("move_san", "?")
                    classification = m.get("classification", "")
                    cp_loss = m.get("cp_loss", 0)
                    lines.append(f"  - {move} ({classification}, -{cp_loss}cp)")
                elif isinstance(m, str):
                    lines.append(f"  - {m}")

        lines.append("")

    if game_num == 0:
        return "No games found."

    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/export.py [progress|games]")
        return 1

    command = sys.argv[1].lower()

    if command == "progress":
        print(export_progress())
    elif command == "games":
        print(export_games())
    else:
        print(f"Unknown command: {command}")
        print("Usage: python scripts/export.py [progress|games]")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
