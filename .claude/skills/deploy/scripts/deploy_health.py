"""Проверка `/health` — общий критерий «выкат доехал» для обеих целей.

`loaded: true` означает, что модель уже в памяти: сервис прогоняет через неё секунду тишины
на старте, поэтому отвечающий, но ещё не прогретый процесс не считается живым.

`curl` запускается с самой целевой машины, а не отсюда. На домашнем сервере порт опубликован
не для всех сетей; на mini сервис слушает адрес WireGuard — из чужой сети его не видно ни в
каком виде. Машина же видит свой сервис всегда.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from deploy_console import DIM, NC, YELLOW, log
from deploy_remote_shell import RemoteShell

CURL_TIMEOUT_S = 10


@dataclass(frozen=True)
class HealthOutcome:
    """Итог опроса. Не исключение: цель сначала печатает логи сервиса, а потом падает."""

    ok: bool
    payload: dict[str, Any] | None
    reason: str


def probe_health(shell: RemoteShell, url: str, *, quiet: bool = False) -> HealthOutcome:
    result = shell.capture(f"curl -sf --max-time {CURL_TIMEOUT_S} {url}", quiet=quiet)
    if result.returncode != 0:
        return HealthOutcome(
            ok=False, payload=None, reason=f"{url} не ответил (curl, код {result.returncode})"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return HealthOutcome(
            ok=False, payload=None, reason=f"{url} ответил не JSON: {result.stdout[:200]!r}"
        )
    if not isinstance(payload, dict):
        return HealthOutcome(
            ok=False, payload=None, reason=f"{url} ответил не объектом: {result.stdout[:200]!r}"
        )
    if not payload.get("loaded"):
        return HealthOutcome(ok=False, payload=payload, reason=f"модель не загружена: {payload}")
    return HealthOutcome(ok=True, payload=payload, reason="")


def wait_for_health(
    shell: RemoteShell, url: str, *, timeout_s: int, poll_s: int
) -> HealthOutcome:
    """Опрос `/health` до готовности или до таймаута.

    Пока сервис поднимается, ответа нет вовсе (порт ещё не слушается) или `loaded: false` —
    обе стадии штатные, и обе здесь просто повод подождать.
    """
    log(YELLOW, f"Жду готовности {url} (до {timeout_s}s)...")
    deadline = time.monotonic() + timeout_s
    outcome = HealthOutcome(ok=False, payload=None, reason="опрос не начинался")
    while time.monotonic() < deadline:
        outcome = probe_health(shell, url, quiet=True)
        if outcome.ok:
            log(DIM, "  ✓ модель загружена")
            return outcome
        print(f"  {DIM}{outcome.reason} — жду {poll_s}s{NC}", flush=True)
        time.sleep(poll_s)
    return HealthOutcome(
        ok=False,
        payload=outcome.payload,
        reason=f"сервис не стал готов за {timeout_s}s (последнее: {outcome.reason})",
    )
