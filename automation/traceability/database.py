"""把过程信号与异常摘要写入一件一码 SQLite 追溯库。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "automation" / "traceability" / "results" / "traceability.db"
DEFAULT_SIGNAL = ROOT / "data" / "samples" / "W2026-001-simulated.json"
DEFAULT_ANOMALY = ROOT / "automation" / "anomaly-detection" / "results" / "W2026-001-anomalies.json"


def ingest(signal_path: Path, anomaly_path: Path, db_path: Path) -> None:
    signal = json.loads(signal_path.read_text(encoding="utf-8"))
    anomaly = json.loads(anomaly_path.read_text(encoding="utf-8"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS weld_sessions (
                sample_id TEXT PRIMARY KEY,
                recorded_at TEXT NOT NULL,
                process TEXT NOT NULL,
                sequence TEXT NOT NULL,
                source_type TEXT NOT NULL,
                anomaly_count INTEGER NOT NULL,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS anomaly_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id TEXT NOT NULL,
                signal TEXT NOT NULL,
                event_type TEXT NOT NULL,
                start_s REAL NOT NULL,
                end_s REAL NOT NULL,
                min_value REAL NOT NULL,
                max_value REAL NOT NULL,
                FOREIGN KEY(sample_id) REFERENCES weld_sessions(sample_id)
            );
            """
        )
        connection.execute(
            """INSERT OR REPLACE INTO weld_sessions
               (sample_id, recorded_at, process, sequence, source_type, anomaly_count, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                signal["sample_id"],
                datetime.now(timezone.utc).isoformat(),
                signal["meta"]["process"],
                signal["meta"]["sequence"],
                "simulated",
                anomaly["event_count"],
                signal["meta"]["notes"],
            ),
        )
        connection.execute("DELETE FROM anomaly_events WHERE sample_id = ?", (signal["sample_id"],))
        connection.executemany(
            """INSERT INTO anomaly_events
               (sample_id, signal, event_type, start_s, end_s, min_value, max_value)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    signal["sample_id"], event["signal"], event["type"], event["start_s"],
                    event["end_s"], event["min"], event["max"],
                )
                for event in anomaly["events"]
            ],
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", type=Path, default=DEFAULT_SIGNAL)
    parser.add_argument("--anomaly", type=Path, default=DEFAULT_ANOMALY)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    ingest(args.signal, args.anomaly, args.db)
    print(f"已写入追溯库: {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

