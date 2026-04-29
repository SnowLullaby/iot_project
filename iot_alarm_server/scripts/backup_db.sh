#!/usr/bin/env bash
set -euo pipefail

STAMP=$(date +%Y%m%d_%H%M%S)
OUT_FILE="backup_${STAMP}.sql"

docker exec -t iot_alarm_postgres pg_dump -U iot_user -d iot_alarm > "$OUT_FILE"
echo "Backup written to $OUT_FILE"
