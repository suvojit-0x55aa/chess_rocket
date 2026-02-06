#!/usr/bin/env bash
set -euo pipefail

echo "=== Chess Speedrun Learning System - Setup ==="
echo ""

# --- Detect OS ---
OS="$(uname -s)"
case "$OS" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)      echo "Unsupported OS: $OS"; exit 1 ;;
esac
echo "Detected platform: $PLATFORM"

# --- Install Stockfish ---
if command -v stockfish &>/dev/null; then
    echo "Stockfish already installed: $(command -v stockfish)"
else
    echo "Installing Stockfish..."
    if [ "$PLATFORM" = "macos" ]; then
        if command -v brew &>/dev/null; then
            brew install stockfish
        else
            echo "ERROR: Homebrew not found. Install Stockfish manually:"
            echo "  brew install stockfish"
            echo "  OR download from https://stockfishchess.org/download/"
            exit 1
        fi
    else
        if command -v apt-get &>/dev/null; then
            sudo apt-get update && sudo apt-get install -y stockfish
        else
            echo "ERROR: apt-get not found. Install Stockfish manually:"
            echo "  sudo apt install stockfish"
            echo "  OR download from https://stockfishchess.org/download/"
            exit 1
        fi
    fi
    echo "Stockfish installed successfully."
fi

# --- Install uv ---
if command -v uv &>/dev/null; then
    echo "uv already installed: $(command -v uv)"
else
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "uv installed successfully."
fi

# --- Project directory ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# --- Sync Python environment ---
echo "Syncing Python environment with uv..."
uv sync --dev
echo "Python environment ready."

# --- Create data directories ---
echo "Creating data directories..."
mkdir -p data/sessions data/games data/lesson_plans
touch data/sessions/.gitkeep data/games/.gitkeep data/lesson_plans/.gitkeep
echo "Data directories created."

# --- Initialize data files ---
if [ ! -f data/progress.json ]; then
    echo '{"current_elo": 400, "sessions_completed": 0, "streak": 0, "accuracy_history": [], "areas_for_improvement": [], "last_session": null}' > data/progress.json
    echo "Initialized data/progress.json"
else
    echo "data/progress.json already exists, skipping."
fi

if [ ! -f data/srs_cards.json ]; then
    echo '[]' > data/srs_cards.json
    echo "Initialized data/srs_cards.json"
else
    echo "data/srs_cards.json already exists, skipping."
fi

echo ""
echo "=== Setup complete! ==="
echo "Run 'python scripts/engine.py play 800' to test the engine."
