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
COPY pyproject.toml uv.lock /app/

# Устанавливаем зависимости без самого проекта — слой переиспользуется,
# пока uv.lock не меняется.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra server

# README нужен hatchling'у только при сборке самого пакета, не при sync зависимостей.
# Копируем отдельно, чтобы изменения README не инвалидировали слой uv sync.
COPY README.md /app/


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
# CUDA runtime нужен ctranslate2 (бэкенд faster-whisper) — либы не бандлятся в wheel.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends curl gnupg2 && \
    curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb \
        -o /tmp/cuda-keyring.deb && \
    dpkg -i /tmp/cuda-keyring.deb && \
    rm /tmp/cuda-keyring.deb && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg=7:5.1.8-0+deb12u1 \
        libcublas-12-6 \
        libcudnn9-cuda-12 && \
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
