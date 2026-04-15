import json
import logging
import os
import time
from typing import Any

import paho.mqtt.client as mqtt

from app.db import get_session
from app.models import AlarmEvent, Telemetry

logger = logging.getLogger(__name__)

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "iot_user")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "iot_password")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "iot/alarm/+/+")


def save_payload(payload: dict[str, Any], source: str = "mqtt") -> None:
    message_type = payload.get("message_type")
    device_id = payload.get("device_id", "unknown")

    with get_session() as session:
        if message_type == "telemetry":
            row = Telemetry(
                device_id=device_id,
                temperature_c=payload.get("temperature_c"),
                humidity_pct=payload.get("humidity_pct"),
                motion=bool(payload.get("motion", False)),
                sound=bool(payload.get("sound", False)),
                wifi_rssi=payload.get("wifi_rssi"),
                uptime_ms=payload.get("uptime_ms"),
                source=source,
                raw_payload=payload,
            )
            session.add(row)
            logger.info("Saved telemetry from %s", device_id)
        elif message_type == "alarm":
            row = AlarmEvent(
                device_id=device_id,
                event_type=payload.get("event_type", "unknown"),
                temperature_c=payload.get("temperature_c"),
                humidity_pct=payload.get("humidity_pct"),
                motion=bool(payload.get("motion", False)),
                sound=bool(payload.get("sound", False)),
                wifi_rssi=payload.get("wifi_rssi"),
                uptime_ms=payload.get("uptime_ms"),
                source=source,
                raw_payload=payload,
            )
            session.add(row)
            logger.info("Saved alarm event from %s", device_id)
        else:
            logger.warning("Unknown message_type: %s", message_type)


class MqttWorker:
    def __init__(self) -> None:
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self._running = False

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Connected to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
            client.subscribe(MQTT_TOPIC, qos=1)
            logger.info("Subscribed to topic %s", MQTT_TOPIC)
        else:
            logger.error("MQTT connection failed: %s", reason_code)

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("Disconnected from MQTT: %s", reason_code)

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            save_payload(payload, source="mqtt")
        except json.JSONDecodeError:
            logger.exception("Failed to decode MQTT JSON on topic %s", msg.topic)
        except Exception:
            logger.exception("Failed to process MQTT message on topic %s", msg.topic)

    def start(self) -> None:
        if self._running:
            return

        self._running = True
        while True:
            try:
                logger.info("Connecting MQTT worker...")
                self.client.connect(MQTT_HOST, MQTT_PORT, 60)
                self.client.loop_start()
                return
            except Exception:
                logger.exception("MQTT worker connection failed, retrying in 5 seconds")
                time.sleep(5)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            logger.exception("Failed to stop MQTT worker cleanly")
