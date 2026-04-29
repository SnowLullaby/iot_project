# IoT Alarm Server v2

Обновлённый сервер для прототипа сигнализации:
- принимает MQTT-сообщения от ESP8266
- сохраняет телеметрию и alarm-события в PostgreSQL
- при alarm публикует команду на ESP32-CAM сделать фото
- принимает JPEG от камеры по HTTP
- хранит путь к фото в БД
- показывает dashboard и страницы событий

## Что сохраняется из старой базы
Старые таблицы `telemetry` и `alarm_events` **не удаляются и не пересоздаются**.
Новая версия просто создаёт дополнительную таблицу `camera_photos`.

## Перед обновлением
```bash
chmod +x scripts/backup_db.sh
./scripts/backup_db.sh
```

## Запуск
```bash
docker compose up -d --build
```

После запуска:
- dashboard: http://213.176.65.184:8000/
- Swagger: http://213.176.65.184:8000/docs
- MQTT broker: 213.176.65.184:1883

## Новый поток данных
1. ESP8266 отправляет telemetry и alarm в MQTT
2. Сервер сохраняет alarm в `alarm_events`
3. Сервер публикует MQTT-команду в `iot/camera/cam-01/capture`
4. ESP32-CAM делает фото и грузит JPEG на `POST /api/photos/upload`
5. Сервер сохраняет файл в `uploads/` и метаданные в `camera_photos`
6. Фото и события видны на сайте

## Полезные адреса
- `GET /api/telemetry`
- `GET /api/events`
- `GET /api/events/{id}`
- `GET /api/photos`
- `GET /api/dashboard`

## Проверка БД
```bash
docker exec -it iot_alarm_postgres psql -U iot_user -d iot_alarm
```

Внутри psql:
```sql
\dt
SELECT id, device_id, received_at, temperature_c, humidity_pct, motion, sound FROM telemetry ORDER BY received_at DESC LIMIT 10;
SELECT id, device_id, received_at, event_type FROM alarm_events ORDER BY received_at DESC LIMIT 10;
SELECT id, alarm_event_id, camera_id, device_id, captured_at, file_path FROM camera_photos ORDER BY captured_at DESC LIMIT 10;
```

## Проверка сайта
- `/` — dashboard
- `/ui/events/<id>` — карточка события и фотографии
