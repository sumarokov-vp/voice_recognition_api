# syntax=docker/dockerfile:1.7

# Зафиксированные версии: обновления делаются явным bump'ом тега.
ARG PYTHON_IMAGE=python:3.14.0-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.10.12

FROM ${UV_IMAGE} AS uv


FROM ${PYTHON_IMAGE} AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=uv /uv /uvx /usr/local/bin/

WORKDIR /app

# Только файлы описания зависимостей. Инвалидируется при изменении uv.lock.
# README нужен hatchling'у для чтения метаданных проекта.
COPY pyproject.toml uv.lock README.md /app/

# Устанавливаем зависимости без самого проекта — слой переиспользуется,
# пока uv.lock не меняется.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra server


FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    HF_HOME=/models \
    HF_HUB_CACHE=/models \
    HF_HUB_DISABLE_XET=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Зафиксированная версия ffmpeg из debian bookworm. При bump'е base-образа
# apt может предложить другую — обновлять осознанно.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg=7:5.1.8-0+deb12u1 && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /models && \
    chmod 1777 /models

WORKDIR /app

# venv из builder'а — тяжёлый слой, меняется только при смене зависимостей.
COPY --from=builder /app/.venv /app/.venv

# Исходники — лёгкий слой, меняется часто; стоит последним, чтобы не инвалидировать
# предыдущие слои. Проект запускается через PYTHONPATH=/app/src, editable-install не нужен.
COPY src /app/src

EXPOSE 8000

CMD ["python", "-m", "api"]
