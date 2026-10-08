"""当前圆环信号与异常结果先核对身份和输入绑定，再写入SQLite。"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "automation/anomaly-detection"))
from anomaly_detector import detect
from hanjie.domain.submission import session_identity

DEFAULT_DB = ROOT / "automation/traceability/results/traceability.db"
DEFAULT_SIGNAL = ROOT / "automation/anomaly-detection/results/W2026-001-signals.json"
DEFAULT_ANOMALY = ROOT / "automation/anomaly-detection/results/W2026-001-anomalies.json"


def ingest(signal_path: Path, anomaly_path: Path, db_path: Path) -> None:
    signal = json.loads(signal_path.read_text(encoding="utf-8"))
    anomaly = json.loads(anomaly_path.read_text(encoding="utf-8"))
    identity = session_identity(signal)
    if any(anomaly.get(name) != value for name, value in identity.items()):
        raise ValueError("信号与异常结果的工件/会话/工艺版本/工序/来源不一致")
    if anomaly != detect(signal):
        raise ValueError("异常结果未绑定本件原始信号，或使用了不同的检测规则/设置")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        # 历史表仍可只读保留；当前表以会话为主键，允许同一工件多次焊接记录。
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS weld_sessions_v2 (
                session_id TEXT PRIMARY KEY,
                sample_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                process_version TEXT NOT NULL,
                operation TEXT NOT NULL,
                sequence_json TEXT NOT NULL,
                source_type TEXT NOT NULL CHECK(source_type IN ('simulated', 'physical')),
                current_definition TEXT NOT NULL,
                temperature_definition TEXT NOT NULL,
                input_digest TEXT NOT NULL,
                detector_revision TEXT NOT NULL,
                anomaly_count INTEGER NOT NULL,
                next_arc_permitted INTEGER NOT NULL,
                notes TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS anomaly_events_v2 (
                session_id TEXT NOT NULL REFERENCES weld_sessions_v2(session_id),
                event_index INTEGER NOT NULL,
                signal TEXT NOT NULL,
                event_type TEXT NOT NULL,
                start_s REAL NOT NULL,
                end_s REAL NOT NULL,
                min_value REAL NOT NULL,
                max_value REAL NOT NULL,
                PRIMARY KEY(session_id, event_index)
            );
        """)
        previous = connection.execute("SELECT sample_id, process_version, source_type, input_digest FROM weld_sessions_v2 WHERE session_id = ?",
                                      (identity["session_id"],)).fetchone()
        binding = (identity["sample_id"], identity["process_version"], identity["source_type"], anomaly["input_digest"])
        if previous is not None:
            if previous != binding:
                raise ValueError("已存在的会话身份/原始信号不得被另一记录覆盖")
            return
        meta = signal["meta"]
        connection.execute("""INSERT INTO weld_sessions_v2
            (session_id,sample_id,recorded_at,process_version,operation,sequence_json,source_type,
             current_definition,temperature_definition,input_digest,detector_revision,anomaly_count,next_arc_permitted,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (identity["session_id"], identity["sample_id"], datetime.now(timezone.utc).isoformat(), identity["process_version"],
             identity["operation"], json.dumps(meta["sequence_segment_ids"]), identity["source_type"],
             meta["current_definition"], meta["temperature_definition"], anomaly["input_digest"],
             anomaly["detector_revision"], anomaly["event_count"], int(anomaly["next_arc_permitted_by_monitor"]), meta.get("notes", "")))
        connection.executemany("""INSERT INTO anomaly_events_v2
            (session_id,event_index,signal,event_type,start_s,end_s,min_value,max_value) VALUES (?,?,?,?,?,?,?,?)""",
            [(identity["session_id"], index, event["signal"], event["type"], event["start_s"], event["end_s"], event["min"], event["max"])
             for index, event in enumerate(anomaly["events"])])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", type=Path, default=DEFAULT_SIGNAL)
    parser.add_argument("--anomaly", type=Path, default=DEFAULT_ANOMALY)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    ingest(args.signal, args.anomaly, args.db)
    print(f"身份核对后已写入当前圆环追溯表 weld_sessions_v2: {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
