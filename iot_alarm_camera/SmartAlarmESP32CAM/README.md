# SmartAlarmESP32CAM

Прошивка для ESP32-CAM (AI Thinker).

## Что делает
- Подключается к Wi-Fi и MQTT
- Подписывается на `iot/camera/<camera_id>/capture`
- По команде делает JPEG-снимок
- Загружает его на сервер по HTTP

## Библиотеки и платы
В Arduino IDE:
- установить пакет плат `esp32 by Espressif Systems`
- установить библиотеку `PubSubClient`
- установить библиотеку `ArduinoJson`

## Подготовка
1. Укажите Wi-Fi, MQTT и `SERVER_UPLOAD_URL`
2. Выберите плату `AI Thinker ESP32-CAM`
3. Загрузите прошивку

## MQTT topics
- subscribe: `iot/camera/<camera_id>/capture`
- publish: `iot/camera/<camera_id>/status`

## Ограничения
- Камера не подключается проводами к NodeMCU с датчиками
- Это отдельный Wi-Fi узел
- Для MVP одно alarm-событие сервера -> один запрос на фото
