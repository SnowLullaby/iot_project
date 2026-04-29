#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <ctype.h>
#include "esp_camera.h"
#include "config.h"

// AI Thinker ESP32-CAM pinout
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

constexpr unsigned long MQTT_RECONNECT_INTERVAL_MS = 5000UL;
constexpr unsigned long CAPTURE_COOLDOWN_MS = 5000UL;

WiFiClient mqttNetClient;
PubSubClient mqttClient(mqttNetClient);

String captureTopic;
String statusTopic;
unsigned long lastMqttReconnectMs = 0;
unsigned long lastCaptureMs = 0;

bool connectWiFi();
bool connectMqtt();
bool initCamera();
void mqttCallback(char* topic, byte* payload, unsigned int length);
void publishStatus(const char* status, const char* details = nullptr);
bool uploadPhoto(int alarmEventId, const char* deviceId, const char* eventType);
String urlEncode(const String& value);

void setup() {
  Serial.begin(115200);
  delay(200);

  if (!initCamera()) {
    Serial.println("Camera init failed.");
  }

  captureTopic = String(CAMERA_TOPIC_ROOT) + "/" + CAMERA_ID + "/capture";
  statusTopic = String(CAMERA_TOPIC_ROOT) + "/" + CAMERA_ID + "/status";

  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setBufferSize(1024);
  mqttClient.setKeepAlive(30);

  connectWiFi();
  connectMqtt();
  publishStatus("online");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  if (!mqttClient.connected()) {
    connectMqtt();
  }

  mqttClient.loop();
  delay(10);
}

bool connectWiFi() {
  Serial.printf("Connecting ESP32-CAM to Wi-Fi: %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startMs < 20000UL) {
    Serial.print('.');
    delay(500);
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi connected. IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }

  Serial.println("Wi-Fi connection timeout.");
  return false;
}

bool connectMqtt() {
  if (mqttClient.connected()) {
    return true;
  }

  if (millis() - lastMqttReconnectMs < MQTT_RECONNECT_INTERVAL_MS) {
    return false;
  }
  lastMqttReconnectMs = millis();

  String clientId = String(CAMERA_ID) + "-cam";
  Serial.printf("Connecting camera to MQTT %s:%d\n", MQTT_HOST, MQTT_PORT);

  bool ok = mqttClient.connect(
      clientId.c_str(),
      MQTT_USERNAME,
      MQTT_PASSWORD,
      statusTopic.c_str(),
      1,
      true,
      "offline");

  if (ok) {
    mqttClient.subscribe(captureTopic.c_str(), 1);
    publishStatus("online");
    Serial.println("Camera MQTT connected.");
    return true;
  }

  Serial.printf("Camera MQTT connect failed, state=%d\n", mqttClient.state());
  return false;
}

bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 15;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("esp_camera_init failed: 0x%x\n", err);
    return false;
  }

  sensor_t* sensor = esp_camera_sensor_get();
  sensor->set_brightness(sensor, 0);
  sensor->set_saturation(sensor, 0);
  return true;
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  Serial.printf("MQTT command on %s\n", topic);

  StaticJsonDocument<512> doc;
  DeserializationError error = deserializeJson(doc, payload, length);
  if (error) {
    Serial.println("Failed to parse camera command JSON.");
    publishStatus("error", "bad_json");
    return;
  }

  const char* command = doc["command"] | "";
  if (strcmp(command, "capture") != 0) {
    return;
  }

  const unsigned long now = millis();
  if (now - lastCaptureMs < CAPTURE_COOLDOWN_MS) {
    publishStatus("skipped", "cooldown");
    return;
  }
  lastCaptureMs = now;

  int alarmEventId = doc["alarm_event_id"] | 0;
  const char* deviceId = doc["device_id"] | SENSOR_DEVICE_ID;
  const char* eventType = doc["event_type"] | "unknown";

  bool uploaded = uploadPhoto(alarmEventId, deviceId, eventType);
  publishStatus(uploaded ? "captured" : "error", uploaded ? "uploaded" : "upload_failed");
}

bool uploadPhoto(int alarmEventId, const char* deviceId, const char* eventType) {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed.");
    return false;
  }

  WiFiClient uploadClient;
  HTTPClient http;

  String url = String(SERVER_UPLOAD_URL) + "?camera_id=" + urlEncode(CAMERA_ID)
      + "&device_id=" + urlEncode(deviceId)
      + "&event_type=" + urlEncode(eventType)
      + "&alarm_event_id=" + String(alarmEventId);

  Serial.println("Uploading photo to server...");
  if (!http.begin(uploadClient, url)) {
    esp_camera_fb_return(fb);
    Serial.println("HTTP begin failed.");
    return false;
  }

  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Upload-Token", CAMERA_UPLOAD_TOKEN);

  int httpCode = http.POST(fb->buf, fb->len);
  String response = http.getString();
  http.end();
  esp_camera_fb_return(fb);

  Serial.printf("Photo upload HTTP %d, response=%s\n", httpCode, response.c_str());
  return httpCode >= 200 && httpCode < 300;
}

void publishStatus(const char* status, const char* details) {
  if (!mqttClient.connected()) {
    return;
  }

  StaticJsonDocument<256> doc;
  doc["camera_id"] = CAMERA_ID;
  doc["message_type"] = "camera_status";
  doc["status"] = status;
  doc["details"] = details ? details : "";
  doc["wifi_rssi"] = (WiFi.status() == WL_CONNECTED) ? WiFi.RSSI() : 0;

  char buffer[320];
  serializeJson(doc, buffer, sizeof(buffer));
  mqttClient.publish(statusTopic.c_str(), buffer, true);
}

String urlEncode(const String& value) {
  String encoded;
  char hex[4];
  for (size_t i = 0; i < value.length(); ++i) {
    const char c = value.charAt(i);
    if (isalnum(static_cast<unsigned char>(c)) || c == '-' || c == '_' || c == '.' || c == '~') {
      encoded += c;
    } else {
      snprintf(hex, sizeof(hex), "%%%02X", static_cast<unsigned char>(c));
      encoded += hex;
    }
  }
  return encoded;
}
