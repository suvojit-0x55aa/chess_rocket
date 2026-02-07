"""Opening recognition library using trie lookup and SQLite queries.

Provides fast opening identification via in-memory trie and rich querying
via SQLite database built by scripts/build_openings_db.py.

Usage:
    from scripts.openings import OpeningsDB
    db = OpeningsDB()
    result = db.identify_opening(["e2e4", "c7c5"])
"""

import json
import os
import random
import sqlite3

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
_DEFAULT_DB = os.path.join(_PROJECT_ROOT, "data", "openings.db")
_DEFAULT_TRIE = os.path.join(_PROJECT_ROOT, "data", "openings_trie.json")

# Common opening families appropriate for beginners (Phase 1: 0-600)
_BEGINNER_FAMILIES = {
    "Italian Game",
    "Sicilian Defense",
    "French Defense",
    "Scandinavian Defense",
    "London System",
    "Queen's Gambit",
    "King's Pawn Game",
    "Philidor Defense",
    "Petrov's Defense",
    "Caro-Kann Defense",
    "Scotch Game",
    "Ruy Lopez",
    "English Opening",
    "Indian Defense",
}


class OpeningsDB:
    """Chess opening recognition and querying.

    Uses an in-memory trie for fast move-sequence lookup and SQLite
    for rich querying by name, ECO code, family, etc.
    """

    def __init__(self, db_path=None, trie_path=None):
        self._db_path = db_path or _DEFAULT_DB
        self._trie_path = trie_path or _DEFAULT_TRIE
        self._trie = self._load_trie()

    def _load_trie(self):
        """Load trie from JSON file. Returns empty dict if unavailable."""
        if not os.path.exists(self._trie_path):
            return {}
        try:
            with open(self._trie_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _get_conn(self):
        """Open a new SQLite connection (thread-safe pattern)."""
        if not os.path.exists(self._db_path):
            return None
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error:
            return None

    def _row_to_dict(self, row):
        """Convert sqlite3.Row to plain dict."""
        return dict(row)

    # ── Trie-based methods ──────────────────────────────────────────

    def identify_opening(self, uci_moves):
        """Identify the deepest matching opening for a sequence of UCI moves.

        Args:
            uci_moves: List of UCI move strings, e.g. ["e2e4", "c7c5"].

        Returns:
            Dict with eco, eco_volume, name, family, pgn, moves_matched keys,
            or None if no match found.
        """
        if not self._trie or not uci_moves:
            return None

        node = self._trie
        best_match = None
        moves_matched = 0

        for i, move in enumerate(uci_moves):
            if move not in node:
                break
            node = node[move]
            if "_eco" in node and "_name" in node:
                eco = node["_eco"]
                name = node["_name"]
                family = name.split(":")[0].strip() if ":" in name else name
                best_match = {
                    "eco": eco,
                    "eco_volume": eco[0] if eco else "",
                    "name": name,
                    "family": family,
                    "moves_matched": i + 1,
                }
                moves_matched = i + 1

        # Enrich with PGN from SQLite if we have a match
        if best_match:
            best_match["pgn"] = self._get_pgn_for_eco_name(
                best_match["eco"], best_match["name"]
            )

        return best_match

    def _get_pgn_for_eco_name(self, eco, name):
        """Look up PGN for a specific opening by ECO + name."""
        conn = self._get_conn()
        if conn is None:
            return ""
        try:
            row = conn.execute(
                "SELECT pgn FROM openings WHERE eco = ? AND name = ? LIMIT 1",
                (eco, name),
            ).fetchone()
            return row["pgn"] if row else ""
        except sqlite3.Error:
            return ""
        finally:
            conn.close()

    def get_continuations(self, uci_moves):
        """Get named openings branching from the current move sequence.

        Args:
            uci_moves: List of UCI move strings for current position.

        Returns:
            List of dicts with eco, name, next_move keys for named
            openings reachable from this position.
        """
        if not self._trie:
            return []

        node = self._trie
        for move in uci_moves:
            if move not in node:
                return []
            node = node[move]

        results = []
        self._collect_named_children(node, [], results, max_depth=4)
        return results

    def _collect_named_children(self, node, path, results, max_depth):
        """Recursively collect named nodes up to max_depth from current node."""
        if max_depth <= 0:
            return
        for key, child in node.items():
            if key.startswith("_"):
                continue
            if not isinstance(child, dict):
                continue
            child_path = path + [key]
            if "_eco" in child and "_name" in child:
                results.append({
                    "eco": child["_eco"],
                    "name": child["_name"],
                    "next_moves": child_path,
                })
            self._collect_named_children(child, child_path, results, max_depth - 1)

    # ── SQLite-based methods ────────────────────────────────────────

    def search_openings(self, query, eco=None, eco_volume=None, limit=20):
        """Search openings by name and/or ECO code using LIKE.

        Args:
            query: Search string (matched against name and eco).
            eco: Optional exact ECO code filter.
            eco_volume: Optional ECO volume filter (A-E).
            limit: Max results to return.

        Returns:
            List of opening dicts, or empty list if DB unavailable.
        """
        conn = self._get_conn()
        if conn is None:
            return []

        try:
            conditions = []
            params = []

            if query:
                conditions.append("(name LIKE ? OR eco LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])
            if eco:
                conditions.append("eco = ?")
                params.append(eco)
            if eco_volume:
                conditions.append("eco_volume = ?")
                params.append(eco_volume)

            where = " AND ".join(conditions) if conditions else "1=1"
            sql = f"SELECT * FROM openings WHERE {where} ORDER BY eco, name LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def get_opening_by_eco(self, eco):
        """Get all openings matching an ECO code.

        Args:
            eco: ECO code string, e.g. "B20".

        Returns:
            List of opening dicts.
        """
        conn = self._get_conn()
        if conn is None:
            return []

        try:
            rows = conn.execute(
                "SELECT * FROM openings WHERE eco = ? ORDER BY name", (eco,)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def get_opening_lines(self, family):
        """Get all variations of an opening family.

        Args:
            family: Opening family name, e.g. "Sicilian Defense".

        Returns:
            List of opening dicts.
        """
        conn = self._get_conn()
        if conn is None:
            return []

        try:
            rows = conn.execute(
                "SELECT * FROM openings WHERE family = ? ORDER BY num_moves, name",
                (family,),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def get_openings_for_level(self, elo):
        """Get level-appropriate openings based on player Elo.

        Phase 1 (0-600): Short openings (<= 4 half-moves) from common families.
        Phase 2 (600-1000): Medium openings (4-10 half-moves).
        Phase 3 (1000+): Full access to all openings.

        Args:
            elo: Player's Elo rating.

        Returns:
            List of opening dicts appropriate for the level.
        """
        conn = self._get_conn()
        if conn is None:
            return []

        try:
            if elo < 600:
                # Phase 1: short, common openings
                placeholders = ",".join("?" for _ in _BEGINNER_FAMILIES)
                rows = conn.execute(
                    f"SELECT * FROM openings WHERE num_moves <= 4 "
                    f"AND family IN ({placeholders}) "
                    f"ORDER BY num_moves, name",
                    list(_BEGINNER_FAMILIES),
                ).fetchall()
            elif elo < 1000:
                # Phase 2: medium-length openings
                rows = conn.execute(
                    "SELECT * FROM openings WHERE num_moves BETWEEN 4 AND 10 "
                    "ORDER BY num_moves, name"
                ).fetchall()
            else:
                # Phase 3: full access
                rows = conn.execute(
                    "SELECT * FROM openings ORDER BY eco, name"
                ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def get_random_opening(self, eco_volume=None, max_moves=None):
        """Get a random opening with optional filters.

        Args:
            eco_volume: Optional ECO volume filter (A-E).
            max_moves: Optional maximum number of half-moves.

        Returns:
            Opening dict, or None if no match or DB unavailable.
        """
        conn = self._get_conn()
        if conn is None:
            return None

        try:
            conditions = []
            params = []

            if eco_volume:
                conditions.append("eco_volume = ?")
                params.append(eco_volume)
            if max_moves is not None:
                conditions.append("num_moves <= ?")
                params.append(max_moves)

            where = " AND ".join(conditions) if conditions else "1=1"
            sql = f"SELECT * FROM openings WHERE {where} ORDER BY RANDOM() LIMIT 1"

            row = conn.execute(sql, params).fetchone()
            return self._row_to_dict(row) if row else None
        except sqlite3.Error:
            return None
        finally:
            conn.close()
