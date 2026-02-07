#!/usr/bin/env python3
"""Build openings database from Lichess chess-openings TSV files.

Downloads 5 TSV files from Lichess GitHub, creates:
  - data/openings.db (SQLite with indexes)
  - data/openings_trie.json (nested dict for fast move lookup)

Usage:
    uv run python scripts/build_openings_db.py
"""

import csv
import io
import json
import os
import sqlite3
import sys
import tempfile
import urllib.request

import chess
import chess.pgn

_BASE_URL = "https://github.com/lichess-org/chess-openings/raw/master"
_TSV_FILES = ["a.tsv", "b.tsv", "c.tsv", "d.tsv", "e.tsv"]

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_RAW_DIR = os.path.join(_DATA_DIR, "openings_raw")
_DB_PATH = os.path.join(_DATA_DIR, "openings.db")
_TRIE_PATH = os.path.join(_DATA_DIR, "openings_trie.json")


def download_tsvs():
    """Download TSV files from Lichess GitHub, caching in data/openings_raw/."""
    os.makedirs(_RAW_DIR, exist_ok=True)
    paths = []
    for fname in _TSV_FILES:
        local_path = os.path.join(_RAW_DIR, fname)
        if os.path.exists(local_path):
            print(f"  Cached: {fname}")
            paths.append(local_path)
            continue
        url = f"{_BASE_URL}/{fname}"
        print(f"  Downloading: {url}")
        try:
            urllib.request.urlretrieve(url, local_path)
        except Exception as e:
            print(f"ERROR: Failed to download {url}", file=sys.stderr)
            print(f"  {e}", file=sys.stderr)
            print("Check your internet connection and try again.", file=sys.stderr)
            sys.exit(1)
        paths.append(local_path)
    return paths


def _pgn_to_uci_and_epd(pgn_text):
    """Convert PGN move text to UCI move list and EPD string."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return "", ""
    board = game.board()
    uci_moves = []
    for move in game.mainline_moves():
        uci_moves.append(move.uci())
        board.push(move)
    uci = " ".join(uci_moves)
    epd = board.epd()
    return uci, epd


def parse_tsvs(paths):
    """Parse downloaded TSV files into a list of opening dicts."""
    openings = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                eco = row.get("eco", "").strip()
                name = row.get("name", "").strip()
                pgn = row.get("pgn", "").strip()

                # Derive UCI and EPD from PGN
                uci, epd = _pgn_to_uci_and_epd(pgn)

                eco_volume = eco[0] if eco else ""
                family = name.split(":")[0].strip() if ":" in name else name
                num_moves = len(uci.split()) if uci else 0

                openings.append({
                    "eco": eco,
                    "eco_volume": eco_volume,
                    "name": name,
                    "family": family,
                    "pgn": pgn,
                    "uci": uci,
                    "epd": epd,
                    "num_moves": num_moves,
                })
    return openings


def build_sqlite(openings):
    """Create SQLite database with openings table and indexes."""
    os.makedirs(_DATA_DIR, exist_ok=True)

    # Build in temp file, then atomically replace
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db", dir=_DATA_DIR)
    os.close(tmp_fd)

    try:
        conn = sqlite3.connect(tmp_path)
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE openings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                eco_volume TEXT NOT NULL,
                eco TEXT NOT NULL,
                name TEXT NOT NULL,
                family TEXT NOT NULL,
                pgn TEXT NOT NULL,
                uci TEXT NOT NULL,
                epd TEXT NOT NULL,
                num_moves INTEGER NOT NULL
            )
        """)

        cur.executemany(
            "INSERT INTO openings (eco_volume, eco, name, family, pgn, uci, epd, num_moves) "
            "VALUES (:eco_volume, :eco, :name, :family, :pgn, :uci, :epd, :num_moves)",
            openings,
        )

        cur.execute("CREATE INDEX idx_eco ON openings(eco)")
        cur.execute("CREATE INDEX idx_eco_volume ON openings(eco_volume)")
        cur.execute("CREATE INDEX idx_family ON openings(family)")
        cur.execute("CREATE INDEX idx_name ON openings(name)")

        conn.commit()
        conn.close()

        os.replace(tmp_path, _DB_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return _DB_PATH


def build_trie(openings):
    """Create a nested dict trie keyed on UCI moves.

    Named nodes have '_eco' and '_name' keys.
    """
    trie = {}
    for opening in openings:
        uci = opening["uci"]
        if not uci:
            continue
        moves = uci.split()
        node = trie
        for move in moves:
            if move not in node:
                node[move] = {}
            node = node[move]
        # Mark this node as a named opening
        node["_eco"] = opening["eco"]
        node["_name"] = opening["name"]

    # Write atomically
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=_DATA_DIR)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(trie, f, separators=(",", ":"))
        os.replace(tmp_path, _TRIE_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return _TRIE_PATH


def main():
    print("=== Building Chess Openings Database ===")
    print()

    print("Step 1: Downloading TSV files...")
    paths = download_tsvs()
    print(f"  {len(paths)} files ready.")
    print()

    print("Step 2: Parsing openings...")
    openings = parse_tsvs(paths)
    print(f"  {len(openings)} openings parsed.")
    print()

    print("Step 3: Building SQLite database...")
    db_path = build_sqlite(openings)
    db_size = os.path.getsize(db_path)
    print(f"  Created: {db_path} ({db_size:,} bytes)")
    print()

    print("Step 4: Building trie index...")
    trie_path = build_trie(openings)
    trie_size = os.path.getsize(trie_path)
    print(f"  Created: {trie_path} ({trie_size:,} bytes)")
    print()

    # Verify counts
    conn = sqlite3.connect(db_path)
    row_count = conn.execute("SELECT COUNT(*) FROM openings").fetchone()[0]
    conn.close()
    print(f"=== Done! {row_count} openings in database ===")

    # Verify trie is under 1MB
    if trie_size > 1_048_576:
        print(f"WARNING: Trie is {trie_size:,} bytes (over 1MB limit)")
    else:
        print(f"Trie size OK: {trie_size:,} bytes (< 1MB)")


if __name__ == "__main__":
    main()
