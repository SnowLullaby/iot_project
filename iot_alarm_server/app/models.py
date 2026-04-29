from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, func
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


class CameraPhoto(Base):
    __tablename__ = "camera_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alarm_event_id: Mapped[int | None] = mapped_column(ForeignKey("alarm_events.id", ondelete="SET NULL"), index=True, nullable=True)
    camera_id: Mapped[str] = mapped_column(String(100), index=True)
    device_id: Mapped[str] = mapped_column(String(100), index=True)
    event_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(100), default="image/jpeg")
    size_bytes: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    source: Mapped[str] = mapped_column(String(20), default="camera_upload")
