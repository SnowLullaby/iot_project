from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(100), index=True)
    received_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    motion: Mapped[bool] = mapped_column(Boolean, default=False)
    sound: Mapped[bool] = mapped_column(Boolean, default=False)
    wifi_rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uptime_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="mqtt")
    raw_payload: Mapped[dict] = mapped_column(JSONB)


class AlarmEvent(Base):
    __tablename__ = "alarm_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(100), index=True)
    received_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    motion: Mapped[bool] = mapped_column(Boolean, default=False)
    sound: Mapped[bool] = mapped_column(Boolean, default=False)
    wifi_rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uptime_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="mqtt")
    raw_payload: Mapped[dict] = mapped_column(JSONB)
