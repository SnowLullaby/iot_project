# IoT Alarm Server (MVP)

Минимальный сервер для проекта сигнализации:
- принимает MQTT-сообщения от ESP8266
- сохраняет телеметрию и alarm-события в PostgreSQL
- даёт простой HTTP API для просмотра данных

## Быстрый старт
```bash
docker compose up --build
```

После запуска:
- HTTP API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- MQTT broker: localhost:1883
- PostgreSQL: localhost:5432

## MQTT topics
Сервер слушает:
- `iot/alarm/+/telemetry`
- `iot/alarm/+/events`
- `iot/alarm/+/status` (статусы не пишет, но их можно расширить позже)

## Примеры API
- `GET /health`
- `GET /api/latest`
- `GET /api/telemetry?limit=50`
- `GET /api/events?limit=50`

## Временное упрощение
В `mosquitto.conf` включён `allow_anonymous true`, чтобы не тормозить MVP.
Позже лучше включить логин/пароль и TLS.
