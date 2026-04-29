import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select

from app.db import get_session
from app.models import AlarmEvent, CameraPhoto, Telemetry

logger = logging.getLogger(__name__)

DEFAULT_CAMERA_ID = os.getenv("DEFAULT_CAMERA_ID", "cam-01")
CAMERA_TOPIC_ROOT = os.getenv("CAMERA_TOPIC_ROOT", "iot/camera")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))


@dataclass
class StoreResult:
    message_type: str | None
    device_id: str
    alarm_event_id: int | None = None
    event_type: str | None = None
    should_request_photo: bool = False


def _boolish(value: Any) -> bool:
    return bool(value)


def store_payload(payload: dict[str, Any], source: str = "mqtt") -> StoreResult:
    message_type = payload.get("message_type")
    device_id = payload.get("device_id", "unknown")

    with get_session() as session:
        if message_type == "telemetry":
            row = Telemetry(
                device_id=device_id,
                temperature_c=payload.get("temperature_c"),
                humidity_pct=payload.get("humidity_pct"),
                motion=_boolish(payload.get("motion", False)),
                sound=_boolish(payload.get("sound", False)),
                wifi_rssi=payload.get("wifi_rssi"),
                uptime_ms=payload.get("uptime_ms"),
                source=source,
                raw_payload=payload,
            )
            session.add(row)
            logger.info("Saved telemetry from %s", device_id)
            return StoreResult(message_type=message_type, device_id=device_id)

        if message_type == "alarm":
            row = AlarmEvent(
                device_id=device_id,
                event_type=payload.get("event_type", "unknown"),
                temperature_c=payload.get("temperature_c"),
                humidity_pct=payload.get("humidity_pct"),
                motion=_boolish(payload.get("motion", False)),
                sound=_boolish(payload.get("sound", False)),
                wifi_rssi=payload.get("wifi_rssi"),
                uptime_ms=payload.get("uptime_ms"),
                source=source,
                raw_payload=payload,
            )
            session.add(row)
            session.flush()
            logger.info("Saved alarm event id=%s from %s", row.id, device_id)
            return StoreResult(
                message_type=message_type,
                device_id=device_id,
                alarm_event_id=row.id,
                event_type=row.event_type,
                should_request_photo=True,
            )

        logger.warning("Unknown message_type: %s", message_type)
        return StoreResult(message_type=message_type, device_id=device_id)


def capture_command_topic(camera_id: str | None = None) -> str:
    cid = camera_id or DEFAULT_CAMERA_ID
    return f"{CAMERA_TOPIC_ROOT}/{cid}/capture"


def build_capture_command(store_result: StoreResult, original_payload: dict[str, Any], camera_id: str | None = None) -> tuple[str, str]:
    cid = camera_id or DEFAULT_CAMERA_ID
    topic = capture_command_topic(cid)
    command = {
        "command": "capture",
        "camera_id": cid,
        "device_id": store_result.device_id,
        "alarm_event_id": store_result.alarm_event_id,
        "event_type": store_result.event_type,
        "motion": original_payload.get("motion", False),
        "sound": original_payload.get("sound", False),
        "trigger_motion": original_payload.get("trigger_motion", False),
        "trigger_sound": original_payload.get("trigger_sound", False),
        "trigger_humidity_low": original_payload.get("trigger_humidity_low", False),
        "trigger_humidity_high": original_payload.get("trigger_humidity_high", False),
    }
    return topic, json.dumps(command)


def store_photo_metadata(
    *,
    camera_id: str,
    device_id: str,
    alarm_event_id: int | None,
    event_type: str | None,
    relative_path: str,
    size_bytes: int,
    content_type: str,
) -> CameraPhoto:
    with get_session() as session:
        row = CameraPhoto(
            camera_id=camera_id,
            device_id=device_id,
            alarm_event_id=alarm_event_id,
            event_type=event_type,
            file_path=relative_path,
            size_bytes=size_bytes,
            content_type=content_type,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return row


def latest_photo_by_event_ids(event_ids: list[int]) -> dict[int, CameraPhoto]:
    if not event_ids:
        return {}

    with get_session() as session:
        rows = session.execute(
            select(CameraPhoto)
            .where(CameraPhoto.alarm_event_id.in_(event_ids))
            .order_by(CameraPhoto.alarm_event_id.asc(), desc(CameraPhoto.captured_at))
        ).scalars().all()

    photos: dict[int, CameraPhoto] = {}
    for row in rows:
        if row.alarm_event_id is not None and row.alarm_event_id not in photos:
            photos[row.alarm_event_id] = row
    return photos
