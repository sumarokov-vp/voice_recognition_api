# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Загрузка per-machine конфигурации Claude-скиллов (``.claude/config.local.yaml``).

Файл gitignored — у каждого разработчика свой. **Секретов внутри нет**: доступ задаётся
несекретными ссылками (имена SSH-алиасов из ``~/.ssh/config`` и пути к записям ``pass``),
а сам секрет достаётся в рантайме через ``pass show <path>``. Шаблон структуры —
``config.local.yaml.example`` (в git).

Структура — верхний уровень ``skills:``, по одной секции на скилл::

    skills:
      deploy:
        prod_ssh_alias: lorsau_odoo
      zadarma:
        credentials_pass_entry: agent_fleet/projects/lorsau/odoo/zadarma_api

Любое значение переопределяется переменной окружения (для CI/разовых прогонов) —
имя env указывается вызывающим кодом.

Скрипты скиллов импортируют этот модуль из ``.claude/lib`` и не парсят конфиг сами.

Текстовым скиллам (bash-рецепты прямо в ``SKILL.md``) доступен CLI — печатает **одно
несекретное** значение, чтобы подставить его в команду::

    ALIAS=$(uv run .claude/lib/machine_config.py deploy prod_ssh_alias) && ssh "$ALIAS" ...

CLI отдаёт только ссылки (алиасы, пути, локальные каталоги). Секреты через него не
проходят: сам секрет берётся отдельным ``pass show "$(… pass_entry)"`` в момент
использования, чтобы не оседать в истории команд и логах.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class ConfigError(RuntimeError):
    """Конфиг отсутствует/неполон или ``pass`` недоступен — с человекочитаемой подсказкой."""


def repo_root() -> Path:
    # .claude/lib/machine_config.py → parents: [0]=lib, [1]=.claude, [2]=корень репо
    return Path(__file__).resolve().parents[2]


def config_path() -> Path:
    return repo_root() / ".claude" / "config.local.yaml"


def load() -> dict[str, Any]:
    """Распарсенный ``config.local.yaml`` (пустой файл → пустой dict)."""
    import yaml

    path = config_path()
    if not path.is_file():
        raise ConfigError(
            f"нет {path}\n"
            "  Скопируй шаблон и впиши свои значения:\n"
            "    cp .claude/config.local.yaml.example .claude/config.local.yaml"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: на верхнем уровне ожидался маппинг (ключ: значение)")
    return data


def skill_section(skill: str) -> dict[str, Any]:
    """Секция ``skills.<skill>`` из конфига (пустой dict, если секции нет)."""
    skills = load().get("skills") or {}
    if not isinstance(skills, dict):
        raise ConfigError(f"{config_path()}: ключ `skills` должен быть маппингом")
    section = skills.get(skill) or {}
    if not isinstance(section, dict):
        raise ConfigError(f"{config_path()}: секция `skills.{skill}` должна быть маппингом")
    return section


def skill_value(skill: str, key: str, *, env: str | None = None) -> str:
    """Значение ``skills.<skill>.<key>`` (env-переменная ``env`` приоритетнее файла).

    ``ConfigError`` с подсказкой, если значение не задано ни там, ни там.
    """
    if env and os.environ.get(env):
        return str(os.environ[env])
    value = skill_section(skill).get(key)
    if not value:
        hint = f" (и нет ${env})" if env else ""
        raise ConfigError(
            f"skills.{skill}.{key} не задан в .claude/config.local.yaml{hint} — "
            "впиши его (структуру см. в config.local.yaml.example)."
        )
    return str(value)


def read_pass_lines(entry: str) -> list[str]:
    """Непустые строки записи ``pass show <entry>`` (значения в вывод/логи не печатаются).

    ``ConfigError`` с подсказкой, если ``pass show`` упал или запись пуста.
    """
    result = subprocess.run(
        ["pass", "show", entry],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise ConfigError(
            f"`pass show {entry}` завершился ошибкой (код {result.returncode})"
            + (f": {stderr}" if stderr else "")
            + "\n  Проверь: запись существует (`pass ls`), gpg-агент разблокирован, "
            "доступ к password-store есть."
        )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    if not lines:
        raise ConfigError(f"pass-запись {entry} пуста")
    return lines


def read_pass_entry(entry: str) -> tuple[str, dict[str, str]]:
    """Прочитать запись ``pass``: строка 1 = основное значение, далее ``ключ=значение``.

    Возвращает ``(значение, поля)``. Значение НИКОГДА не печатается в текст ошибок/логов.
    Для одностроковых записей (один секрет) ``поля`` пустой, значение = строка 1.
    """
    lines = read_pass_lines(entry)
    primary = lines[0]
    fields: dict[str, str] = {}
    for raw in lines[1:]:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()
    return primary, fields


def lookup(skill: str, dotted_key: str) -> str:
    """Значение ``skills.<skill>.<a>.<b>…`` по точечному пути (для вложенных секций)."""
    node: Any = skill_section(skill)
    walked: list[str] = []
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            path = ".".join([skill, *walked, part])
            raise ConfigError(
                f"skills.{path} не задан в {config_path()} — впиши его (структуру см. в config.local.yaml.example)."
            )
        node = node[part]
        walked.append(part)
    if isinstance(node, (dict, list)):
        raise ConfigError(f"skills.{skill}.{dotted_key} — это секция, а не одно значение")
    return str(node)


def _main(argv: list[str]) -> int:
    """CLI: печатает одно НЕсекретное значение из конфига (см. докстринг модуля)."""
    args = [a for a in argv if a != "--"]
    if len(args) != 2:
        print(
            "usage: machine_config.py <skill> <key[.subkey...]>\n"
            "  печатает значение skills.<skill>.<key> из .claude/config.local.yaml\n"
            "  пример: ALIAS=$(uv run .claude/lib/machine_config.py deploy prod_ssh_alias)",
            file=sys.stderr,
        )
        return 2
    try:
        print(lookup(args[0], args[1]))
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
