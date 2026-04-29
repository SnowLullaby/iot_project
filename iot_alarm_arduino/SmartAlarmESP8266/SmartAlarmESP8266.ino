#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include "config.h"

// -----------------------------
// Pin mapping for NodeMCU v3 (ESP8266)
// D5 -> GPIO14 -> DHT11 DATA
// D6 -> GPIO12 -> HC-SR501 OUT
// D7 -> GPIO13 -> FC-04 DO
// -----------------------------

constexpr uint8_t DHT_PIN = D5;
constexpr uint8_t PIR_PIN = D6;
constexpr uint8_t SOUND_PIN = D7;
constexpr uint8_t DHT_TYPE = DHT11;

constexpr unsigned long SENSOR_READ_INTERVAL_MS = 5000UL;
constexpr unsigned long TELEMETRY_INTERVAL_MS = 10UL * 60UL * 1000UL;  // 10 minutes
constexpr unsigned long RECONNECT_INTERVAL_MS = 5000UL;
constexpr unsigned long EVENT_COOLDOWN_MS = 30000UL;                   // 30 seconds
constexpr int WIFI_CONNECT_TIMEOUT_MS = 20000;

// Runtime thresholds. Can be changed from server via MQTT config topic.
float humidityLowThreshold = 30.0f;
float humidityHighThreshold = 70.0f;
float temperatureLowThreshold = 18.0f;
float temperatureHighThreshold = 30.0f;

// FC-04 modules often have configurable digital output polarity.
// If your logs show inverted values, change LOW <-> HIGH.
constexpr uint8_t SOUND_ACTIVE_STATE = LOW;

DHT dht(DHT_PIN, DHT_TYPE);
WiFiClient espClient;
PubSubClient mqttClient(espClient);

struct SensorSnapshot {
  float temperatureC = NAN;
  float humidityPct = NAN;
  bool motionDetected = false;
  bool soundDetected = false;
  int wifiRssi = 0;
  unsigned long uptimeMs = 0;
  bool validDht = false;

  bool humidityLow = false;
  bool humidityHigh = false;
  bool temperatureLow = false;
  bool temperatureHigh = false;
};

SensorSnapshot currentSnapshot;
SensorSnapshot lastGoodSnapshot;

unsigned long lastSensorReadMs = 0;
unsigned long lastTelemetryMs = 0;
unsigned long lastReconnectAttemptMs = 0;

unsigned long lastMotionEventMs = 0;
unsigned long lastSoundEventMs = 0;
unsigned long lastHumidityEventMs = 0;
unsigned long lastTemperatureEventMs = 0;

String baseTopic;
String telemetryTopic;
String eventsTopic;
String statusTopic;
String configTopic;

void connectWiFi();
bool ensureMqttConnected();
void readSensors();
void publishTelemetry(const char* reason);
void publishAlarmEvent(
  const char* eventType,
  bool triggerMotion,
  bool triggerSound,
  bool triggerHumidityLow,
  bool triggerHumidityHigh,
  bool triggerTemperatureLow,
  bool triggerTemperatureHigh
);
void publishStatus(const char* status);
void buildPayload(JsonDocument& doc, const char* messageType, const char* reason = nullptr, const char* eventType = nullptr);
void mqttCallback(char* topic, byte* payload, unsigned int length);

void setup() {
  Serial.begin(115200);
  delay(100);

  pinMode(PIR_PIN, INPUT);
  pinMode(SOUND_PIN, INPUT);

  dht.begin();

  baseTopic = String(MQTT_TOPIC_ROOT) + "/" + DEVICE_ID;
  telemetryTopic = baseTopic + "/telemetry";
  eventsTopic = baseTopic + "/events";
  statusTopic = baseTopic + "/status";
  configTopic = baseTopic + "/config";

  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setBufferSize(1024);
  mqttClient.setKeepAlive(30);
  mqttClient.setCallback(mqttCallback);

  connectWiFi();
  ensureMqttConnected();
  publishStatus("online");

  readSensors();
  publishTelemetry("boot");
  lastTelemetryMs = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  ensureMqttConnected();
  mqttClient.loop();

  const unsigned long now = millis();

  if (now - lastSensorReadMs >= SENSOR_READ_INTERVAL_MS) {
    lastSensorReadMs = now;
    readSensors();

    const bool motionTrigger =
      currentSnapshot.motionDetected &&
      (now - lastMotionEventMs >= EVENT_COOLDOWN_MS);

    const bool soundTrigger =
      currentSnapshot.soundDetected &&
      (now - lastSoundEventMs >= EVENT_COOLDOWN_MS);

    const bool humidityLowTrigger =
      currentSnapshot.validDht &&
      currentSnapshot.humidityLow &&
      (now - lastHumidityEventMs >= EVENT_COOLDOWN_MS);

    const bool humidityHighTrigger =
      currentSnapshot.validDht &&
      currentSnapshot.humidityHigh &&
      (now - lastHumidityEventMs >= EVENT_COOLDOWN_MS);

    const bool temperatureLowTrigger =
      currentSnapshot.validDht &&
      currentSnapshot.temperatureLow &&
      (now - lastTemperatureEventMs >= EVENT_COOLDOWN_MS);

    const bool temperatureHighTrigger =
      currentSnapshot.validDht &&
      currentSnapshot.temperatureHigh &&
      (now - lastTemperatureEventMs >= EVENT_COOLDOWN_MS);

    const int triggerCount =
      (motionTrigger ? 1 : 0) +
      (soundTrigger ? 1 : 0) +
      (humidityLowTrigger ? 1 : 0) +
      (humidityHighTrigger ? 1 : 0) +
      (temperatureLowTrigger ? 1 : 0) +
      (temperatureHighTrigger ? 1 : 0);

    if (triggerCount > 0) {
      if (motionTrigger) {
        lastMotionEventMs = now;
      }
      if (soundTrigger) {
        lastSoundEventMs = now;
      }
      if (humidityLowTrigger || humidityHighTrigger) {
        lastHumidityEventMs = now;
      }
      if (temperatureLowTrigger || temperatureHighTrigger) {
        lastTemperatureEventMs = now;
      }

      const char* eventType = "multi";
      if (triggerCount == 1) {
        if (motionTrigger) {
          eventType = "motion";
        } else if (soundTrigger) {
          eventType = "sound";
        } else if (humidityLowTrigger) {
          eventType = "humidity_low";
        } else if (humidityHighTrigger) {
          eventType = "humidity_high";
        } else if (temperatureLowTrigger) {
          eventType = "temperature_low";
        } else {
          eventType = "temperature_high";
        }
      }

      publishAlarmEvent(
        eventType,
        motionTrigger,
        soundTrigger,
        humidityLowTrigger,
        humidityHighTrigger,
        temperatureLowTrigger,
        temperatureHighTrigger
      );
    }
  }

  if (now - lastTelemetryMs >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryMs = now;
    publishTelemetry("scheduled");
  }
}

void connectWiFi() {
  Serial.printf("Connecting to Wi-Fi: %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const unsigned long startMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startMs < WIFI_CONNECT_TIMEOUT_MS) {
    delay(500);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi connected. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi connection timeout.");
  }
}

bool ensureMqttConnected() {
  if (mqttClient.connected()) {
    return true;
  }

  const unsigned long now = millis();
  if (now - lastReconnectAttemptMs < RECONNECT_INTERVAL_MS) {
    return false;
  }
  lastReconnectAttemptMs = now;

  String clientId = String(DEVICE_ID) + "-" + String(ESP.getChipId(), HEX);

  Serial.printf("Connecting to MQTT broker %s:%d...\n", MQTT_HOST, MQTT_PORT);
  const bool connected = mqttClient.connect(
      clientId.c_str(),
      MQTT_USERNAME,
      MQTT_PASSWORD,
      statusTopic.c_str(),
      1,
      true,
      "offline");

  if (connected) {
    Serial.println("MQTT connected.");
    mqttClient.subscribe(configTopic.c_str(), 1);
    publishStatus("online");
    return true;
  }

  Serial.printf("MQTT connect failed, state=%d\n", mqttClient.state());
  return false;
}

void readSensors() {
  currentSnapshot.motionDetected = digitalRead(PIR_PIN) == HIGH;
  currentSnapshot.soundDetected = digitalRead(SOUND_PIN) == SOUND_ACTIVE_STATE;
  currentSnapshot.wifiRssi = (WiFi.status() == WL_CONNECTED) ? WiFi.RSSI() : 0;
  currentSnapshot.uptimeMs = millis();

  const float humidity = dht.readHumidity();
  const float temperature = dht.readTemperature();

  if (!isnan(humidity) && !isnan(temperature)) {
    currentSnapshot.humidityPct = humidity;
    currentSnapshot.temperatureC = temperature;
    currentSnapshot.validDht = true;
    lastGoodSnapshot = currentSnapshot;
  } else {
    currentSnapshot.validDht = false;
    currentSnapshot.humidityPct = lastGoodSnapshot.humidityPct;
    currentSnapshot.temperatureC = lastGoodSnapshot.temperatureC;
    Serial.println("DHT read failed, using last good values.");
  }

  currentSnapshot.humidityLow = currentSnapshot.validDht && currentSnapshot.humidityPct < humidityLowThreshold;
  currentSnapshot.humidityHigh = currentSnapshot.validDht && currentSnapshot.humidityPct > humidityHighThreshold;
  currentSnapshot.temperatureLow = currentSnapshot.validDht && currentSnapshot.temperatureC < temperatureLowThreshold;
  currentSnapshot.temperatureHigh = currentSnapshot.validDht && currentSnapshot.temperatureC > temperatureHighThreshold;

  Serial.printf(
      "T=%.2fC H=%.2f%% Motion=%d Sound=%d RSSI=%d\n",
      currentSnapshot.temperatureC,
      currentSnapshot.humidityPct,
      currentSnapshot.motionDetected,
      currentSnapshot.soundDetected,
      currentSnapshot.wifiRssi);
}

void publishTelemetry(const char* reason) {
  if (!ensureMqttConnected()) {
    return;
  }

  StaticJsonDocument<512> doc;
  buildPayload(doc, "telemetry", reason, nullptr);

  char payload[640];
  serializeJson(doc, payload, sizeof(payload));

  const bool ok = mqttClient.publish(telemetryTopic.c_str(), payload, false);
  Serial.printf("Telemetry publish: %s\n", ok ? "OK" : "FAILED");
}

void publishAlarmEvent(
  const char* eventType,
  bool triggerMotion,
  bool triggerSound,
  bool triggerHumidityLow,
  bool triggerHumidityHigh,
  bool triggerTemperatureLow,
  bool triggerTemperatureHigh
) {
  if (!ensureMqttConnected()) {
    return;
  }

  StaticJsonDocument<512> doc;
  buildPayload(doc, "alarm", nullptr, eventType);
  doc["trigger_motion"] = triggerMotion;
  doc["trigger_sound"] = triggerSound;
  doc["trigger_humidity_low"] = triggerHumidityLow;
  doc["trigger_humidity_high"] = triggerHumidityHigh;
  doc["trigger_temperature_low"] = triggerTemperatureLow;
  doc["trigger_temperature_high"] = triggerTemperatureHigh;

  char payload[640];
  serializeJson(doc, payload, sizeof(payload));

  const bool ok = mqttClient.publish(eventsTopic.c_str(), payload, false);
  Serial.printf("Alarm publish [%s]: %s\n", eventType, ok ? "OK" : "FAILED");
}

void publishStatus(const char* status) {
  if (!mqttClient.connected()) {
    return;
  }
  mqttClient.publish(statusTopic.c_str(), status, true);
}

void buildPayload(JsonDocument& doc, const char* messageType, const char* reason, const char* eventType) {
  doc["device_id"] = DEVICE_ID;
  doc["message_type"] = messageType;
  doc["temperature_c"] = currentSnapshot.temperatureC;
  doc["humidity_pct"] = currentSnapshot.humidityPct;
  doc["motion"] = currentSnapshot.motionDetected;
  doc["sound"] = currentSnapshot.soundDetected;
  doc["wifi_rssi"] = currentSnapshot.wifiRssi;
  doc["uptime_ms"] = currentSnapshot.uptimeMs;
  doc["dht_ok"] = currentSnapshot.validDht;

  doc["humidity_low_threshold"] = humidityLowThreshold;
  doc["humidity_high_threshold"] = humidityHighThreshold;
  doc["temperature_low_threshold"] = temperatureLowThreshold;
  doc["temperature_high_threshold"] = temperatureHighThreshold;

  if (reason != nullptr) {
    doc["reason"] = reason;
  }
  if (eventType != nullptr) {
    doc["event_type"] = eventType;
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  if (String(topic) != configTopic) {
    return;
  }

  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, payload, length);
  if (error) {
    Serial.println("Failed to parse config JSON");
    return;
  }

  if (doc["humidity_low_threshold"].is<float>()) {
    humidityLowThreshold = doc["humidity_low_threshold"].as<float>();
  }
  if (doc["humidity_high_threshold"].is<float>()) {
    humidityHighThreshold = doc["humidity_high_threshold"].as<float>();
  }
  if (doc["temperature_low_threshold"].is<float>()) {
    temperatureLowThreshold = doc["temperature_low_threshold"].as<float>();
  }
  if (doc["temperature_high_threshold"].is<float>()) {
    temperatureHighThreshold = doc["temperature_high_threshold"].as<float>();
  }

  Serial.printf(
    "Config updated: H[%.1f..%.1f] T[%.1f..%.1f]\n",
    humidityLowThreshold,
    humidityHighThreshold,
    temperatureLowThreshold,
    temperatureHighThreshold
  );
}
