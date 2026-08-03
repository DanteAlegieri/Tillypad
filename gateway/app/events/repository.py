from __future__ import annotations
import json, sqlite3
from pathlib import Path
from .models import Event, utc_now
from .types import EventType, EventSeverity, EventSource, EventStatus

class SQLiteEventRepository:
    def __init__(self,path:str|Path):
        self.path=str(path)
        self.initialize()

    def connect(self):
        c=sqlite3.connect(self.path)
        c.row_factory=sqlite3.Row
        return c

    def initialize(self):
        expected_columns = [
            "id", "snapshot_id", "agent_id", "event_type",
            "severity", "source", "title", "description",
            "payload_json", "score", "status", "created_at",
            "acknowledged_at", "resolved_at",
        ]

        with self.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='events'"
            ).fetchone() is not None

            if exists:
                info = connection.execute(
                    "PRAGMA table_info(events)"
                ).fetchall()
                columns = [row["name"] for row in info]
                id_row = next(
                    (row for row in info if row["name"] == "id"),
                    None,
                )
                id_type = (
                    str(id_row["type"] or "").upper()
                    if id_row is not None
                    else ""
                )

                if columns != expected_columns or id_type not in {"TEXT", ""}:
                    connection.execute(
                        "ALTER TABLE events RENAME TO events_legacy"
                    )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    acknowledged_at TEXT,
                    resolved_at TEXT
                )
                """
            )

            legacy_exists = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='events_legacy'"
            ).fetchone() is not None

            if legacy_exists:
                legacy_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(events_legacy)"
                    ).fetchall()
                }

                if {"id", "agent_id", "title"} <= legacy_columns:
                    rows = connection.execute(
                        "SELECT * FROM events_legacy"
                    ).fetchall()

                    for row in rows:
                        data = dict(row)
                        legacy_id = str(data.get("id") or "")
                        if not legacy_id:
                            continue

                        connection.execute(
                            """
                            INSERT OR IGNORE INTO events (
                                id, snapshot_id, agent_id, event_type,
                                severity, source, title, description,
                                payload_json, score, status, created_at,
                                acknowledged_at, resolved_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                legacy_id,
                                str(
                                    data.get("snapshot_id")
                                    or f"legacy:{legacy_id}"
                                ),
                                str(data.get("agent_id") or "unknown"),
                                str(
                                    data.get("event_type")
                                    or "snapshot_created"
                                ),
                                str(data.get("severity") or "info"),
                                str(data.get("source") or "system"),
                                str(
                                    data.get("title")
                                    or "Старое событие"
                                ),
                                str(data.get("description") or ""),
                                str(data.get("payload_json") or "{}"),
                                int(data.get("score") or 0),
                                str(data.get("status") or "archived"),
                                str(data.get("created_at") or ""),
                                data.get("acknowledged_at"),
                                data.get("resolved_at"),
                            ),
                        )

                connection.execute("DROP TABLE events_legacy")

            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_agent_created "
                "ON events(agent_id, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_status "
                "ON events(agent_id, status, created_at DESC)"
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup
                ON events(agent_id, snapshot_id, event_type, title)
                """
            )

    def save(self, event: Event) -> Event:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO events (
                    id, snapshot_id, agent_id, event_type,
                    severity, source, title, description,
                    payload_json, score, status, created_at,
                    acknowledged_at, resolved_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.id),
                    str(event.snapshot_id),
                    str(event.agent_id),
                    event.event_type.value,
                    event.severity.value,
                    event.source.value,
                    event.title,
                    event.description,
                    json.dumps(
                        event.payload,
                        ensure_ascii=False,
                    ),
                    int(event.score),
                    event.status.value,
                    event.created_at,
                    event.acknowledged_at,
                    event.resolved_at,
                ),
            )
        return event

    def list(self,agent_id:str,status:EventStatus|None=None,
             source:EventSource|None=None,severity:EventSeverity|None=None,
             limit:int=100)->list[Event]:
        cond=["agent_id=?"]; params=[agent_id]
        for field,val in (("status",status),("source",source),("severity",severity)):
            if val is not None:
                cond.append(f"{field}=?"); params.append(val.value)
        params.append(max(1,min(limit,500)))
        with self.connect() as c:
            rows=c.execute(
              f"SELECT * FROM events WHERE {' AND '.join(cond)} "
              "ORDER BY score DESC,created_at DESC LIMIT ?",params
            ).fetchall()
        return [self._row(r) for r in rows]

    def get(self,event_id:str)->Event|None:
        with self.connect() as c:
            r=c.execute("SELECT * FROM events WHERE id=?",(event_id,)).fetchone()
        return self._row(r) if r else None

    def set_status(self,event_id:str,status:EventStatus)->Event|None:
        ack=utc_now() if status==EventStatus.ACKNOWLEDGED else None
        done=utc_now() if status in (EventStatus.DONE,EventStatus.ARCHIVED) else None
        with self.connect() as c:
            c.execute('''UPDATE events SET status=?,
              acknowledged_at=COALESCE(?,acknowledged_at),
              resolved_at=COALESCE(?,resolved_at) WHERE id=?''',
              (status.value,ack,done,event_id))
        return self.get(event_id)

    @staticmethod
    def _row(r):
        return Event(
          id=r["id"],snapshot_id=r["snapshot_id"],agent_id=r["agent_id"],
          event_type=EventType(r["event_type"]),severity=EventSeverity(r["severity"]),
          source=EventSource(r["source"]),title=r["title"],
          description=r["description"],payload=json.loads(r["payload_json"] or "{}"),
          score=int(r["score"]),status=EventStatus(r["status"]),
          created_at=r["created_at"],acknowledged_at=r["acknowledged_at"],
          resolved_at=r["resolved_at"])
