from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Guest(Base):
    __tablename__ = "guests"

    gest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    division_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    state_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)

    date_open: Mapped[str | None] = mapped_column(String(64), nullable=True)
    date_close: Mapped[str | None] = mapped_column(String(64), nullable=True)

    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    order_sum: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    pay_sum: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    raw_json: Mapped[str] = mapped_column(Text, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
