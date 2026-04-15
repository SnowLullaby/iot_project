# SmartAlarmESP8266

Минимальная прошивка для NodeMCU v3 (ESP8266) с датчиками:
- DHT11 (температура/влажность)
- HC-SR501 (движение)
- FC-04 (шум, цифровой пороговый выход)

## Пины
- D5 (GPIO14) -> DHT11 DATA
- D6 (GPIO12) -> HC-SR501 OUT
- D7 (GPIO13) -> FC-04 DO
- 3V3/VIN/GND -> питание в зависимости от вашего модуля

## Библиотеки Arduino IDE
Установить через Library Manager:
- DHT sensor library by Adafruit
- PubSubClient by Nick O'Leary
- ArduinoJson by Benoit Blanchon

## Что делает прошивка
- Читает датчики каждые 5 секунд
- Отправляет телеметрию раз в 30 секунд
- Сразу отправляет alarm-событие при:
  - обнаружении движения
  - обнаружении шума выше порога FC-04
  - выходе влажности за диапазон 30..70%

## Подготовка
1. Укажите Wi-Fi и пароль в config.h
2. Выберите в Arduino IDE плату `NodeMCU 1.0 (ESP-12E Module)`
3. Загрузите скетч

## MQTT topics
- `iot/alarm/<device_id>/telemetry`
- `iot/alarm/<device_id>/events`
- `iot/alarm/<device_id>/status`

## Примечание по FC-04
У FC-04 порог шума задаётся потенциометром на модуле.
Если логика срабатывания инвертирована, в `.ino` поменяйте:
`SOUND_ACTIVE_STATE = LOW` на `HIGH`.
