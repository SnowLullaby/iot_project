import logging
import math
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from app.db import get_session, engine
from app.models import AlarmEvent, Base, CameraPhoto, Telemetry
from app.mqtt_worker import MqttWorker
from app.services import build_capture_command
from app.services import UPLOAD_DIR, latest_photo_by_event_ids, store_payload, store_photo_metadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

PHOTO_UPLOAD_TOKEN = os.getenv("PHOTO_UPLOAD_TOKEN", "change_me_upload_token")
MEDIA_URL_PREFIX = "/media"

mqtt_worker = MqttWorker()
templates = Jinja2Templates(directory="templates")


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
    trigger_motion: bool | None = None
    trigger_sound: bool | None = None
    trigger_humidity_low: bool | None = None
    trigger_humidity_high: bool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    mqtt_worker.start()
    yield
    mqtt_worker.stop()


app = FastAPI(title="IoT Alarm Server", version="0.2.2", lifespan=lifespan)
app.mount(MEDIA_URL_PREFIX, StaticFiles(directory=UPLOAD_DIR), name="media")


def photo_public_url(row: CameraPhoto | None) -> str | None:
    if row is None:
        return None
    return f"{MEDIA_URL_PREFIX}/{row.file_path}"


def serialize_telemetry(row: Telemetry) -> dict[str, Any]:
    return {
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


def serialize_event(row: AlarmEvent, photo_url: str | None = None) -> dict[str, Any]:
    return {
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
        "photo_url": photo_url,
    }


def serialize_photo(row: CameraPhoto) -> dict[str, Any]:
    return {
        "id": row.id,
        "alarm_event_id": row.alarm_event_id,
        "camera_id": row.camera_id,
        "device_id": row.device_id,
        "event_type": row.event_type,
        "captured_at": row.captured_at,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "url": photo_public_url(row),
    }


def build_page_payload(items: list[dict[str, Any]], total: int, page: int, per_page: int) -> dict[str, Any]:
    pages = max(1, math.ceil(total / per_page)) if per_page > 0 else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "has_prev": page > 1,
        "has_next": page < pages,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/ui/events/{event_id}", response_class=HTMLResponse)
def event_detail_page(request: Request, event_id: int):
    with get_session() as session:
        event = session.get(AlarmEvent, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        event_data = serialize_event(event)

        photos = session.execute(
            select(CameraPhoto)
            .where(CameraPhoto.alarm_event_id == event_id)
            .order_by(desc(CameraPhoto.captured_at))
        ).scalars().all()
        photo_data = [serialize_photo(photo) for photo in photos]

    return templates.TemplateResponse(
        "event_detail.html",
        {
            "request": request,
            "event": event_data,
            "photos": photo_data,
        },
    )


@app.get("/ui/telemetry/{telemetry_id}", response_class=HTMLResponse)
def telemetry_detail_page(request: Request, telemetry_id: int):
    with get_session() as session:
        row = session.get(Telemetry, telemetry_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Telemetry row not found")
        telemetry_data = serialize_telemetry(row)

    return templates.TemplateResponse(
        "telemetry_detail.html",
        {
            "request": request,
            "telemetry": telemetry_data,
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/ingest")
def ingest(payload: IngestPayload) -> dict[str, str]:
    result = store_payload(payload.model_dump(), source="http")
    if result.should_request_photo and result.alarm_event_id is not None and mqtt_worker.client.connected():
        topic, command = build_capture_command(result, payload.model_dump())
        mqtt_worker.client.publish(topic, command, qos=1, retain=False)
    return {"status": "stored"}


@app.post("/api/photos/upload")
async def upload_photo(
    request: Request,
    camera_id: str,
    device_id: str,
    alarm_event_id: int | None = None,
    event_type: str | None = None,
    x_upload_token: str | None = Header(default=None),
):
    if x_upload_token != PHOTO_UPLOAD_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid upload token")

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty body")

    now = datetime.now(timezone.utc)
    relative_dir = Path(str(now.year), f"{now.month:02d}", f"{now.day:02d}")
    file_name = f"{now.strftime('%H%M%S')}_{camera_id}_{device_id}_{alarm_event_id or 'none'}_{uuid.uuid4().hex[:8]}.jpg"
    absolute_dir = UPLOAD_DIR / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)
    absolute_path = absolute_dir / file_name
    absolute_path.write_bytes(body)

    stored_row = store_photo_metadata(
        camera_id=camera_id,
        device_id=device_id,
        alarm_event_id=alarm_event_id,
        event_type=event_type,
        relative_path=str(relative_dir / file_name),
        size_bytes=len(body),
        content_type="image/jpeg",
    )

    return {
        "status": "stored",
        "photo_id": stored_row.id,
        "url": photo_public_url(stored_row),
    }


@app.get("/api/latest")
def latest(device_id: str | None = None) -> dict[str, Any]:
    with get_session() as session:
        stmt = select(Telemetry).order_by(desc(Telemetry.received_at)).limit(1)
        if device_id:
            stmt = (
                select(Telemetry)
                .where(Telemetry.device_id == device_id)
                .order_by(desc(Telemetry.received_at))
                .limit(1)
            )
        row = session.execute(stmt).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="No telemetry yet")
        return row.raw_payload


@app.get("/api/telemetry")
def telemetry(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
    device_id: str | None = None,
) -> dict[str, Any]:
    offset = (page - 1) * per_page

    with get_session() as session:
        stmt = select(Telemetry)
        count_stmt = select(func.count()).select_from(Telemetry)

        if device_id:
            stmt = stmt.where(Telemetry.device_id == device_id)
            count_stmt = count_stmt.where(Telemetry.device_id == device_id)

        total = session.execute(count_stmt).scalar_one()
        rows = session.execute(
            stmt.order_by(desc(Telemetry.received_at)).offset(offset).limit(per_page)
        ).scalars().all()

        items = [serialize_telemetry(row) for row in rows]

    return build_page_payload(items, total, page, per_page)


@app.get("/api/telemetry/{telemetry_id}")
def telemetry_detail(telemetry_id: int) -> dict[str, Any]:
    with get_session() as session:
        row = session.get(Telemetry, telemetry_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Telemetry row not found")
        return serialize_telemetry(row)


@app.get("/api/events")
def events(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
    device_id: str | None = None,
) -> dict[str, Any]:
    offset = (page - 1) * per_page

    with get_session() as session:
        stmt = select(AlarmEvent)
        count_stmt = select(func.count()).select_from(AlarmEvent)

        if device_id:
            stmt = stmt.where(AlarmEvent.device_id == device_id)
            count_stmt = count_stmt.where(AlarmEvent.device_id == device_id)

        total = session.execute(count_stmt).scalar_one()
        rows = session.execute(
            stmt.order_by(desc(AlarmEvent.received_at)).offset(offset).limit(per_page)
        ).scalars().all()

        event_ids = [row.id for row in rows]
        photo_map = latest_photo_by_event_ids(event_ids)
        items = [serialize_event(row, photo_public_url(photo_map.get(row.id))) for row in rows]

    return build_page_payload(items, total, page, per_page)


@app.get("/api/events/{event_id}")
def event_detail(event_id: int) -> dict[str, Any]:
    with get_session() as session:
        event = session.get(AlarmEvent, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")

        event_data = serialize_event(event)

        photos = session.execute(
            select(CameraPhoto)
            .where(CameraPhoto.alarm_event_id == event_id)
            .order_by(desc(CameraPhoto.captured_at))
        ).scalars().all()
        photo_data = [serialize_photo(photo) for photo in photos]

    return {
        "event": event_data,
        "photos": photo_data,
    }


@app.get("/api/photos")
def photos(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=8, ge=1, le=100),
    device_id: str | None = None,
) -> dict[str, Any]:
    offset = (page - 1) * per_page

    with get_session() as session:
        stmt = select(CameraPhoto)
        count_stmt = select(func.count()).select_from(CameraPhoto)

        if device_id:
            stmt = stmt.where(CameraPhoto.device_id == device_id)
            count_stmt = count_stmt.where(CameraPhoto.device_id == device_id)

        total = session.execute(count_stmt).scalar_one()
        rows = session.execute(
            stmt.order_by(desc(CameraPhoto.captured_at)).offset(offset).limit(per_page)
        ).scalars().all()

        items = [serialize_photo(row) for row in rows]

    return build_page_payload(items, total, page, per_page)


@app.get("/api/dashboard")
def dashboard_data() -> dict[str, Any]:
    with get_session() as session:
        telemetry_rows = session.execute(
            select(Telemetry).order_by(desc(Telemetry.received_at)).limit(10)
        ).scalars().all()
        event_rows = session.execute(
            select(AlarmEvent).order_by(desc(AlarmEvent.received_at)).limit(10)
        ).scalars().all()
        photo_rows = session.execute(
            select(CameraPhoto).order_by(desc(CameraPhoto.captured_at)).limit(8)
        ).scalars().all()

        event_ids = [row.id for row in event_rows]
        photo_map = latest_photo_by_event_ids(event_ids)

        telemetry_items = [serialize_telemetry(row) for row in telemetry_rows]
        event_items = [serialize_event(row, photo_public_url(photo_map.get(row.id))) for row in event_rows]
        photo_items = [serialize_photo(row) for row in photo_rows]

    return {
        "telemetry": telemetry_items,
        "events": event_items,
        "photos": photo_items,
    }
