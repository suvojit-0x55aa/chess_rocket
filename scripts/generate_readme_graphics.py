"""Generate README graphics using Nanobanan (Gemini Image API).

Usage: uv run --with google-genai python scripts/generate_readme_graphics.py [name...]
Names: hero-banner, architecture, features (default: all)
"""

import os
import sys
from pathlib import Path

from google import genai


def load_api_key():
    """Load NANOBANANA_API_KEY from aikyam .env file."""
    env_path = Path.home() / "REDACTED"
    if not env_path.exists():
        print(f"Error: .env not found at {env_path}")
        sys.exit(1)
    for line in env_path.read_text().splitlines():
        if line.startswith("NANOBANANA_API_KEY="):
            return line.split("=", 1)[1].strip()
    print("Error: NANOBANANA_API_KEY not found in .env")
    sys.exit(1)


PROMPTS = {
    "hero-banner": (
        "Create a wide banner image (1200x400 pixels) for a GitHub repository called 'Chess Rocket'. "
        "Show a stylized chess board with a small rocket launching upward from it, leaving a trail of light. "
        "The text 'Chess Rocket' should appear prominently in a clean, modern sans-serif font. "
        "Use a dark background (deep navy/charcoal) with bright accent colors (electric blue, white, hints of orange from the rocket). "
        "The style should be flat/modern illustration, suitable for a tech project README. "
        "Clean, minimal, professional. No photorealism. Wide panoramic format."
    ),
    "architecture": (
        "Create a clean infographic diagram showing software architecture data flow. "
        "Left side: a box labeled 'Claude Code (Tutor Agent)' with a brain/AI icon. "
        "Center: arrows labeled 'MCP Protocol' flowing to a large box labeled 'MCP Server (FastMCP)' "
        "containing sub-boxes: 'GameEngine (Stockfish)', 'OpeningsDB (3,627)', 'SRS (SM-2)', '17+ Tools'. "
        "Right side: arrow to 'Web Dashboard' box with a chess board icon. "
        "Bottom: arrow from MCP Server down to 'data/' storage icon. "
        "Use a dark background with chess-themed accents (knight piece silhouettes as decorative elements). "
        "Colors: deep navy background, white text, electric blue boxes, orange accent lines. "
        "Clean flat design, no 3D effects. Readable text labels. Horizontal layout ~1000x500 pixels."
    ),
    "features": (
        "Create a horizontal feature highlights strip for a chess learning app README. "
        "Show 5 feature cards in a row, each with an icon and short label: "
        "1) A difficulty slider icon with 'Adaptive Difficulty (100-3500 Elo)' "
        "2) A book/database icon with '3,627 Openings' "
        "3) A puzzle piece icon with '284 Puzzles' "
        "4) A brain with clock icon with 'Spaced Repetition (SM-2)' "
        "5) A dashboard/monitor icon with 'Web Dashboard' "
        "Dark background (navy/charcoal), white text, each card has a subtle glowing border in electric blue. "
        "Modern flat design, clean icons, professional look. Wide format ~1200x300 pixels. "
        "Chess-themed subtle decorative elements in the background."
    ),
}


def generate_graphic(client, name, prompt, output_dir):
    """Generate a single graphic and save it."""
    output_path = output_dir / f"{name}.png"
    print(f"\nGenerating {name}...")

    response = client.models.generate_content(
        model="nano-banana-pro-preview",
        contents=[prompt],
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data:
            output_path.write_bytes(part.inline_data.data)
            size_kb = output_path.stat().st_size / 1024
            print(f"  Saved: {output_path} ({size_kb:.0f} KB)")
            return True

    print(f"  Error: No image returned for {name}")
    if response.candidates[0].content.parts:
        text = response.candidates[0].content.parts[0].text
        print(f"  Response text: {text[:200]}")
    return False


def main():
    api_key = load_api_key()
    client = genai.Client(api_key=api_key)

    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir.parent / "assets"
    output_dir.mkdir(exist_ok=True)

    targets = sys.argv[1:] if len(sys.argv) > 1 else list(PROMPTS.keys())

    results = {}
    for name in targets:
        if name not in PROMPTS:
            print(f"Unknown graphic: {name}. Available: {', '.join(PROMPTS.keys())}")
            continue
        results[name] = generate_graphic(client, name, PROMPTS[name], output_dir)

    print("\n--- Results ---")
    for name, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
