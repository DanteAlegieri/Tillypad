from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.division import Division
from app.models.guest import Guest
from app.models.sync_log import SyncLog


def get_dashboard_data(
    db: Session,
    date_prefix: str | None = None,
) -> dict:
    filters = []
    if date_prefix:
        filters.append(Guest.date_open.like(f"{date_prefix}%"))

    stats_stmt = select(
        func.count(Guest.gest_id),
        func.coalesce(func.sum(Guest.order_sum), 0),
        func.coalesce(func.sum(Guest.pay_sum), 0),
        func.coalesce(
            func.avg(
                case(
                    (Guest.order_sum != 0, Guest.order_sum),
                    else_=None,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(case((Guest.state_id == 0, 1), else_=0)),
            0,
        ),
        func.coalesce(
            func.sum(case((Guest.state_id == 1, 1), else_=0)),
            0,
        ),
    ).where(*filters)

    row = db.execute(stats_stmt).one()

    recent_stmt = (
        select(Guest)
        .where(*filters)
        .order_by(Guest.updated_at.desc())
        .limit(20)
    )

    divisions = db.execute(
        select(Division).order_by(Division.name)
    ).scalars().all()

    sync_logs = db.execute(
        select(SyncLog)
        .order_by(SyncLog.id.desc())
        .limit(10)
    ).scalars().all()

    return {
        "checks_count": int(row[0] or 0),
        "order_sum": float(row[1] or 0),
        "pay_sum": float(row[2] or 0),
        "avg_check": float(row[3] or 0),
        "open_count": int(row[4] or 0),
        "closed_count": int(row[5] or 0),
        "recent": db.execute(recent_stmt).scalars().all(),
        "divisions": divisions,
        "last_sync": sync_logs,
    }
