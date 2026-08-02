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
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS events(
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
            );
            CREATE INDEX IF NOT EXISTS idx_events_agent_created
            ON events(agent_id,created_at DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup
            ON events(agent_id,snapshot_id,event_type,title);
            ''')

    def save(self,event:Event)->Event:
        with self.connect() as c:
            c.execute('''
            INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',(
              event.id,event.snapshot_id,event.agent_id,event.event_type.value,
              event.severity.value,event.source.value,event.title,event.description,
              json.dumps(event.payload,ensure_ascii=False),event.score,event.status.value,
              event.created_at,event.acknowledged_at,event.resolved_at
            ))
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
