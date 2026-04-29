# SmartAlarmESP8266

Прошивка для NodeMCU v3 (ESP8266) с датчиками:
- DHT11 (температура/влажность)
- HC-SR501 (движение)
- FC-04 (шум, цифровой пороговый выход)

## Пины
- D5 (GPIO14) -> DHT11 DATA
- D6 (GPIO12) -> HC-SR501 OUT
- D7 (GPIO13) -> FC-04 DO

## Питание
- DHT11: 3V + G
- FC-04: 3V + G
- HC-SR501: лучше VU + G

## Библиотеки Arduino IDE
Установить через Library Manager:
- DHT sensor library by Adafruit
- Adafruit Unified Sensor
- PubSubClient by Nick O'Leary
- ArduinoJson by Benoit Blanchon

## Что делает прошивка
- Читает датчики каждые 5 секунд
- Отправляет телеметрию раз в 10 минут
- Отправляет alarm-событие не чаще, чем раз в 30 секунд
- Если несколько триггеров сработали в одном цикле, отправляет **одно** alarm-событие с `event_type=multi`

## Подготовка
1. Укажите Wi-Fi и пароль в config.h
2. Выберите в Arduino IDE плату `NodeMCU 1.0 (ESP-12E Module)`
3. Загрузите скетч
4. Откройте Serial Monitor на скорости `115200`

## MQTT topics
- `iot/alarm/<device_id>/telemetry`
- `iot/alarm/<device_id>/events`
- `iot/alarm/<device_id>/status`

## Примечание по FC-04
У FC-04 порог шума задаётся потенциометром на модуле.
Если логика срабатывания инвертирована, в `.ino` поменяйте:
`SOUND_ACTIVE_STATE = LOW` на `HIGH`.
