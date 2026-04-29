#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

echo "=== Деплой voice-recognition ==="

cd "$PROJECT_DIR"

echo "--- Пересборка образа и запуск контейнера ---"
docker compose up -d --build

echo "--- Ожидание healthcheck (до 120s) ---"
for i in $(seq 1 24); do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' voice-recognition 2>/dev/null || echo "missing")
    if [ "$STATUS" = "healthy" ]; then
        echo "Контейнер healthy."
        break
    elif [ "$STATUS" = "unhealthy" ]; then
        echo "Контейнер unhealthy. Логи:"
        docker compose logs voice-recognition --tail=50
        exit 1
    fi
    echo "  ($i/24) статус: $STATUS — ждём 5s..."
    sleep 5
done

echo "--- Проверка /health ---"
curl -sf http://localhost:8000/health && echo ""

echo "=== Деплой завершён ==="
