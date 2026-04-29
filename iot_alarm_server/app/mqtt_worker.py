import json
import logging
import os
import time

import paho.mqtt.client as mqtt

from app.services import build_capture_command, store_payload

logger = logging.getLogger(__name__)

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "iot_user")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "iot_password")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "iot/alarm/+/+")


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
            result = store_payload(payload, source="mqtt")
            if result.should_request_photo and result.alarm_event_id is not None:
                topic, command = build_capture_command(result, payload)
                info = client.publish(topic, command, qos=1, retain=False)
                logger.info(
                    "Published camera capture request for event_id=%s to %s (mid=%s)",
                    result.alarm_event_id,
                    topic,
                    info.mid,
                )
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

