"""Append-only SQLite event store with versioned full-envelope SHA-256 chains."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Optional


SCHEMA_VERSION = 2


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class EventStore:
    def __init__(self, db_path: str, read_only: bool = False):
        self.db_path = db_path
        self.read_only = read_only
        target = f"file:{db_path}?mode=ro" if read_only else db_path
        self.conn = sqlite3.connect(target, uri=read_only)
        self.conn.row_factory = sqlite3.Row
        if not read_only:
            self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                turn INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                timestamp REAL NOT NULL,
                data_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                model TEXT,
                condition TEXT,
                seed INTEGER,
                sequence_no INTEGER,
                prev_hash TEXT,
                envelope_hash TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_run_agent ON events(run_id, agent_id);
            CREATE INDEX IF NOT EXISTS idx_event_type ON events(run_id, event_type);
            CREATE INDEX IF NOT EXISTS idx_content_hash ON events(content_hash);
            CREATE TABLE IF NOT EXISTS run_metadata (
                run_id TEXT PRIMARY KEY,
                config_json TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL,
                status TEXT DEFAULT 'running',
                total_cost REAL DEFAULT 0.0,
                agent_count INTEGER DEFAULT 0,
                total_turns INTEGER DEFAULT 0,
                schema_version INTEGER DEFAULT 1,
                manifest_hash TEXT,
                final_chain_head TEXT
            );
            CREATE TABLE IF NOT EXISTS event_chains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                prev_hash TEXT,
                next_hash TEXT,
                created_at REAL NOT NULL
            );
        """)
        # Migrate Phase 0 databases without rewriting their evidence.
        self._ensure_columns("events", {
            "sequence_no": "INTEGER", "prev_hash": "TEXT", "envelope_hash": "TEXT"})
        self._ensure_columns("run_metadata", {
            "schema_version": "INTEGER DEFAULT 1", "manifest_hash": "TEXT",
            "final_chain_head": "TEXT"})
        self.conn.commit()

    def _ensure_columns(self, table: str, columns: dict[str, str]):
        present = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        for name, declaration in columns.items():
            if name not in present:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    @staticmethod
    def _hash_content(data: dict) -> str:
        """Legacy Phase 0 payload hash."""
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]

    @staticmethod
    def _payload_hash(data: dict) -> str:
        return hashlib.sha256(canonical_json(data).encode()).hexdigest()

    @staticmethod
    def _envelope_hash(envelope: dict) -> str:
        return hashlib.sha256(canonical_json(envelope).encode()).hexdigest()

    def init_run(self, run_id: str, config: dict, manifest_hash: str = ""):
        existing = self.conn.execute(
            "SELECT run_id FROM run_metadata WHERE run_id = ?", (run_id,)).fetchone()
        if existing:
            raise ValueError(f"run already exists: {run_id}")
        self.conn.execute(
            """INSERT INTO run_metadata
               (run_id, config_json, start_time, status, schema_version, manifest_hash)
               VALUES (?, ?, ?, 'running', ?, ?)""",
            (run_id, canonical_json(config), time.time(), SCHEMA_VERSION, manifest_hash))
        self.conn.commit()

    def finish_run(self, run_id: str, total_cost: float, agent_count: int,
                   total_turns: int, status: str = "completed"):
        if status not in {"completed", "halted"}:
            raise ValueError(f"invalid final run status: {status}")
        head = self.chain_head(run_id)
        self.conn.execute(
            """UPDATE run_metadata SET end_time=?, status=?, total_cost=?,
               agent_count=?, total_turns=?, final_chain_head=? WHERE run_id=?""",
            (time.time(), status, total_cost, agent_count, total_turns, head, run_id))
        self.conn.commit()

    def log(self, run_id: str, agent_id: str, turn: int, event_type: str,
            data: dict, model: str = "", condition: str = "", seed: int = 0):
        ts = time.time()
        row = self.conn.execute(
            "SELECT sequence_no, envelope_hash FROM events WHERE run_id=? ORDER BY id DESC LIMIT 1",
            (run_id,)).fetchone()
        sequence_no = ((row["sequence_no"] or 0) + 1) if row else 1
        prev_hash = (row["envelope_hash"] if row and row["envelope_hash"] else "genesis")
        envelope = {"run_id": run_id, "agent_id": agent_id, "turn": turn,
                    "event_type": event_type, "timestamp": ts, "data": data,
                    "model": model, "condition": condition, "seed": seed,
                    "sequence_no": sequence_no, "prev_hash": prev_hash}
        payload_hash = self._payload_hash(data)
        envelope_hash = self._envelope_hash(envelope)
        self.conn.execute(
            """INSERT INTO events
               (run_id,agent_id,turn,event_type,timestamp,data_json,content_hash,
                model,condition,seed,sequence_no,prev_hash,envelope_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, agent_id, turn, event_type, ts, canonical_json(data), payload_hash,
             model, condition, seed, sequence_no, prev_hash, envelope_hash))
        # Retained for readers of the Phase 0 schema; v2 verification uses the
        # envelope columns in the event itself.
        self.conn.execute(
            "INSERT INTO event_chains (run_id,prev_hash,next_hash,created_at) VALUES (?,?,?,?)",
            (run_id, prev_hash, envelope_hash, ts))
        self.conn.commit()
        return envelope_hash

    def chain_head(self, run_id: str) -> str:
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(events)")}
        selection = "envelope_hash,content_hash" if "envelope_hash" in columns else "content_hash"
        row = self.conn.execute(
            f"SELECT {selection} FROM events WHERE run_id=? ORDER BY id DESC LIMIT 1",
            (run_id,)).fetchone()
        if not row:
            return "genesis"
        return ((row["envelope_hash"] or row["content_hash"])
                if "envelope_hash" in columns else row["content_hash"])

    def query(self, run_id: str, event_type: Optional[str] = None,
              agent_id: Optional[str] = None, limit: int = 100) -> list[dict]:
        sql, params = "SELECT * FROM events WHERE run_id=?", [run_id]
        if event_type:
            sql += " AND event_type=?"; params.append(event_type)
        if agent_id:
            sql += " AND agent_id=?"; params.append(agent_id)
        sql += " ORDER BY id ASC LIMIT ?"; params.append(limit)
        return [dict(row) for row in self.conn.execute(sql, params)]

    def verify_chain(self, run_id: str) -> dict:
        events = self.conn.execute(
            "SELECT * FROM events WHERE run_id=? ORDER BY id ASC", (run_id,)).fetchall()
        if not events:
            return {"version": SCHEMA_VERSION, "total": 0, "verified": 0, "breaks": []}
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(events)")}
        if "envelope_hash" in columns and events[0]["envelope_hash"]:
            return self._verify_v2(events)
        return self._verify_legacy(run_id, events)

    def _verify_v2(self, events) -> dict:
        report = {"version": 2, "total": len(events), "verified": 0, "breaks": []}
        prev = "genesis"
        for expected_sequence, event in enumerate(events, 1):
            data = json.loads(event["data_json"])
            envelope = {"run_id": event["run_id"], "agent_id": event["agent_id"],
                        "turn": event["turn"], "event_type": event["event_type"],
                        "timestamp": event["timestamp"], "data": data,
                        "model": event["model"] or "", "condition": event["condition"] or "",
                        "seed": event["seed"], "sequence_no": event["sequence_no"],
                        "prev_hash": event["prev_hash"]}
            problems = []
            if event["sequence_no"] != expected_sequence: problems.append("sequence_mismatch")
            if event["prev_hash"] != prev: problems.append("previous_hash_mismatch")
            if event["content_hash"] != self._payload_hash(data): problems.append("payload_hash_mismatch")
            if event["envelope_hash"] != self._envelope_hash(envelope): problems.append("envelope_hash_mismatch")
            if problems:
                report["breaks"].append({"event_id": event["id"], "reasons": problems})
            else:
                report["verified"] += 1
            prev = event["envelope_hash"]
        return report

    def _verify_legacy(self, run_id: str, events) -> dict:
        report = {"version": 1, "total": len(events), "verified": 0, "breaks": []}
        rows = self.conn.execute(
            "SELECT * FROM event_chains WHERE run_id=? ORDER BY id ASC", (run_id,)).fetchall()
        if len(rows) != len(events):
            report["breaks"].append({"reason": "chain_length_mismatch"})
        prev = "genesis"
        for index, event in enumerate(events):
            computed = self._hash_content(json.loads(event["data_json"]))
            chain = rows[index] if index < len(rows) else None
            if computed != event["content_hash"]:
                report["breaks"].append({"event_id": event["id"], "reason": "content_hash_mismatch"})
            elif chain and chain["prev_hash"] != prev:
                report["breaks"].append({"event_id": event["id"], "reason": "chain_break"})
            else:
                report["verified"] += 1
            prev = event["content_hash"]
        return report

    def get_run_summary(self, run_id: str) -> dict:
        meta = self.conn.execute("SELECT * FROM run_metadata WHERE run_id=?", (run_id,)).fetchone()
        if not meta:
            return {}
        counts = {r["event_type"]: r["cnt"] for r in self.conn.execute(
            "SELECT event_type,COUNT(*) cnt FROM events WHERE run_id=? GROUP BY event_type", (run_id,))}
        return {"run_id": run_id, "status": meta["status"],
                "duration_s": (meta["end_time"] or time.time()) - meta["start_time"],
                "total_cost": meta["total_cost"], "agent_count": meta["agent_count"],
                "total_turns": meta["total_turns"], "event_counts": counts,
                "final_chain_head": meta["final_chain_head"]}

    def close(self):
        self.conn.close()
