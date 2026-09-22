"""Печать и запуск локальных команд — общий словарь выката для обеих целей.

Модуль импортируется точкой входа `deploy-prod.py` и обеими целями; своих зависимостей
у него нет, inline-метаданные PEP 723 лежат только на точке входа.
"""

from __future__ import annotations

import subprocess
from typing import Any

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
DIM = "\033[2m"
RED = "\033[0;31m"
NC = "\033[0m"


class PreflightError(RuntimeError):
    """Префлайт красный — выкат остановлен, живой сервис не тронут.

    Отдельный тип нужен точке входа: префлайт выходит с кодом 2 и печатает, что на целевой
    машине ничего не изменилось, — в отличие от падения посреди выката.
    """


def log(color: str, message: str) -> None:
    print(f"{color}{message}{NC}", flush=True)


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Локальная команда с трассировкой. `check=True`: упавший шаг обязан остановить выкат."""
    print(f"→ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, check=True, **kwargs)


def echo_output(result: subprocess.CompletedProcess[str], indent: str = "    ") -> None:
    """Показать собранный вывод команды. Нужен на разборе падения: захваченные логи
    сервиса бесполезны, если их никто не печатает."""
    for stream in (result.stdout, result.stderr):
        for line in (stream or "").splitlines():
            print(f"{indent}{DIM}{line}{NC}", flush=True)


def plural(count: int, one: str, few: str, many: str) -> str:
    """Русское склонение по числу. Числа здесь — сама грамматика, а не магические константы."""
    tail, hundred = count % 10, count % 100
    if tail == 1 and hundred != 11:  # noqa: PLR2004
        return one
    if 2 <= tail <= 4 and not 12 <= hundred <= 14:  # noqa: PLR2004
        return few
    return many
