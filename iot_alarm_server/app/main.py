import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from app.db import get_session, engine
from app.models import AlarmEvent, Base, Telemetry
from app.mqtt_worker import MqttWorker, save_payload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

mqtt_worker = MqttWorker()


class IngestPayload(BaseModel):
    device_id: str = Field(..., examples=["alarm-node-01"])
    message_type: str = Field(..., examples=["telemetry", "alarm"])
    event_type: str | None = None
    temperature_c: float | None = None
    humidity_pct: float | None = None
    motion: bool = False
    sound: bool = False
    wifi_rssi: int | None = None
    uptime_ms: int | None = None
    dht_ok: bool | None = None
    reason: str | None = None
    humidity_low_threshold: float | None = None
    humidity_high_threshold: float | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    mqtt_worker.start()
    yield
    mqtt_worker.stop()


app = FastAPI(title="IoT Alarm Server", version="0.1.0", lifespan=lifespan)


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "iot-alarm-server",
        "status": "ok",
        "endpoints": ["/health", "/api/latest", "/api/telemetry", "/api/events", "/api/ingest"],
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/ingest")
def ingest(payload: IngestPayload) -> dict[str, str]:
    save_payload(payload.model_dump(), source="http")
    return {"status": "stored"}


@app.get("/api/latest")
def latest(device_id: str | None = None) -> dict[str, Any]:
    with get_session() as session:
        stmt = select(Telemetry).order_by(desc(Telemetry.received_at)).limit(1)
        if device_id:
            stmt = select(Telemetry).where(Telemetry.device_id == device_id).order_by(desc(Telemetry.received_at)).limit(1)
        row = session.execute(stmt).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="No telemetry yet")
        return row.raw_payload


@app.get("/api/telemetry")
def telemetry(
    limit: int = Query(default=100, ge=1, le=1000),
    device_id: str | None = None,
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(Telemetry).order_by(desc(Telemetry.received_at)).limit(limit)
        if device_id:
            stmt = select(Telemetry).where(Telemetry.device_id == device_id).order_by(desc(Telemetry.received_at)).limit(limit)
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "id": row.id,
                "device_id": row.device_id,
                "received_at": row.received_at,
                "temperature_c": row.temperature_c,
                "humidity_pct": row.humidity_pct,
                "motion": row.motion,
                "sound": row.sound,
                "wifi_rssi": row.wifi_rssi,
                "uptime_ms": row.uptime_ms,
                "source": row.source,
                "raw_payload": row.raw_payload,
            }
            for row in rows
        ]


@app.get("/api/events")
def events(
    limit: int = Query(default=100, ge=1, le=1000),
    device_id: str | None = None,
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(AlarmEvent).order_by(desc(AlarmEvent.received_at)).limit(limit)
        if device_id:
            stmt = select(AlarmEvent).where(AlarmEvent.device_id == device_id).order_by(desc(AlarmEvent.received_at)).limit(limit)
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "id": row.id,
                "device_id": row.device_id,
                "received_at": row.received_at,
                "event_type": row.event_type,
                "temperature_c": row.temperature_c,
                "humidity_pct": row.humidity_pct,
                "motion": row.motion,
                "sound": row.sound,
                "wifi_rssi": row.wifi_rssi,
                "uptime_ms": row.uptime_ms,
                "source": row.source,
                "raw_payload": row.raw_payload,
            }
            for row in rows
        ]
