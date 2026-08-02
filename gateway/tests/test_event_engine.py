
from pathlib import Path
from app.events import EventEngine, Snapshot, SQLiteEventRepository

def test_events(tmp_path:Path):
    repo=SQLiteEventRepository(tmp_path/"e.db")
    engine=EventEngine(repo)
    prev=Snapshot("1","g","2026-08-02","2026-08-02T10:00:00+00:00",10000,20,500)
    cur=Snapshot("2","g","2026-08-02","2026-08-02T11:00:00+00:00",12000,22,545)
    types={e.event_type.value for e in engine.process_snapshot(cur,prev)}
    assert "snapshot_created" in types
    assert "revenue_growth" in types
    assert "average_check_growth" in types
