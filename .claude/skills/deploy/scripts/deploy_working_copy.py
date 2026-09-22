"""Шапка «что уезжает»: ветка, коммит, неотправленные коммиты и состояние рабочей копии.

Печатается первой на обеих целях — до префлайта и до любого обращения к машине. Уезжает
рабочая копия как есть, а не коммит, поэтому грязное дерево — факт выката, а не деталь: по
SHA потом не восстановить, что именно уехало.

Набор путей, по которым считается грязность, у каждой цели свой: на домашний сервер едет
`Dockerfile` и compose, на mini — нет. Поэтому пути приезжают снаружи, от цели.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath

from deploy_console import DIM, GREEN, NC, RED, YELLOW, log, plural

# Сколько каталогов показывать в разбивке грязного дерева.
DIRTY_GROUPS_SHOWN = 8


@dataclass(frozen=True)
class Change:
    kind: str
    path: str


@dataclass(frozen=True)
class WorkingCopy:
    """Снимок того, что уедет: git-координаты плюс расхождение с ними на диске."""

    branch: str
    commit: str
    unpushed: int | None  # None — у ветки нет upstream, сравнивать не с чем
    changes: tuple[Change, ...]
    paths: tuple[str, ...]  # по каким путям считалась грязность — они же и уезжают
    readable: bool  # False — git не ответил; состояние неизвестно, но выкат не блокируем

    @property
    def is_dirty(self) -> bool:
        return bool(self.changes)


def git_output(*args: str) -> str | None:
    """stdout git-команды либо None, если git ответил ошибкой: инструмент отчёта не должен
    останавливать выкат."""
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.rstrip("\n") if result.returncode == 0 else None


def change_kind(index_code: str, worktree_code: str) -> str:
    codes = index_code + worktree_code
    if "?" in codes:
        return "вне git"
    if "R" in codes:
        return "переименовано"
    if "A" in codes:
        return "добавлено"
    if "D" in codes:
        return "удалено"
    return "изменено"


def parse_status_line(line: str) -> Change | None:
    # `git status --porcelain`: два кода состояния, пробел, путь — короче быть нечему.
    if len(line) < 4:  # noqa: PLR2004
        return None
    path = line[3:]
    if " -> " in path:  # переименование: важен путь назначения, он и уедет
        path = path.split(" -> ", 1)[1]
    return Change(change_kind(line[0], line[1]), path.strip('"'))


def change_group(path: str) -> str:
    """Каталог, по которому группируются изменения: слой внутри src, иначе — родитель файла."""
    parts = PurePosixPath(path).parts
    if parts[0] == "src" and len(parts) > 3:  # noqa: PLR2004 — src/<пакет>/<слой>/<файл>
        return "/".join(parts[:3])
    return str(PurePosixPath(path).parent)


def read_working_copy(paths: tuple[str, ...]) -> WorkingCopy:
    branch = git_output("rev-parse", "--abbrev-ref", "HEAD")
    commit = git_output("log", "-1", "--format=%h %ad %s", "--date=format:%d.%m.%Y %H:%M")
    status = git_output("status", "--porcelain", "-uall", "--", *paths)
    if branch is None or commit is None or status is None:
        return WorkingCopy("?", "?", None, (), paths, readable=False)
    ahead = git_output("rev-list", "--count", "@{upstream}..HEAD")
    changes = tuple(
        change
        for change in (parse_status_line(line) for line in status.splitlines() if line)
        if change is not None
    )
    return WorkingCopy(
        branch="detached HEAD" if branch == "HEAD" else branch,
        commit=commit,
        unpushed=int(ahead) if ahead is not None and ahead.isdigit() else None,
        changes=changes,
        paths=paths,
        readable=True,
    )


def print_working_copy(state: WorkingCopy) -> None:
    """Печатается всегда и первой — до префлайта и до любого обращения к машине."""
    log(YELLOW, "Что уезжает:")
    if not state.readable:
        log(RED, "  состояние рабочей копии определить не удалось (git не ответил)")
        return
    unpushed = ""
    if state.unpushed:
        commits = plural(state.unpushed, "коммит", "коммита", "коммитов")
        unpushed = f"{RED}  ← не отправлено в origin: {state.unpushed} {commits}{NC}"
    elif state.unpushed is None:
        unpushed = f"{DIM}  ← upstream не настроен{NC}"
    print(f"  ветка   {state.branch}{unpushed}", flush=True)
    print(f"  коммит  {state.commit}", flush=True)
    if not state.is_dirty:
        print(f"  дерево  {GREEN}чистое{NC} — уедет ровно этот коммит", flush=True)
        return

    total = len(state.changes)
    files = plural(total, "изменение", "изменения", "изменений")
    print(f"  дерево  {RED}ГРЯЗНОЕ{NC}: {total} {files} в выкатываемых путях", flush=True)
    print(f"          {DIM}{', '.join(state.paths)}{NC}", flush=True)
    kinds = Counter(change.kind for change in state.changes)
    print(
        "          " + " · ".join(f"{kind} {count}" for kind, count in kinds.most_common()),
        flush=True,
    )
    groups = Counter(change_group(change.path) for change in state.changes)
    for group, count in groups.most_common(DIRTY_GROUPS_SHOWN):
        print(f"          {DIM}{group:<40}{NC} {count}", flush=True)
    hidden = len(groups) - DIRTY_GROUPS_SHOWN
    if hidden > 0:
        catalogs = plural(hidden, "каталог", "каталога", "каталогов")
        print(f"          {DIM}… и ещё {hidden} {catalogs}{NC}", flush=True)
    revision = state.commit.split()[0]
    print(f"  {RED}уедет не коммит {revision}, а рабочая копия как есть{NC}", flush=True)
