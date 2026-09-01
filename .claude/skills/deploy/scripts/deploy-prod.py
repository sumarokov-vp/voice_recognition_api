# /// script
# requires-python = ">=3.14"  # `except A, B:` без скобок — PEP 758, только 3.14+
# dependencies = ["pyyaml"]
# ///
"""Выкат voice_recognition на сервер: исходники туда → сборка образа ТАМ → перезапуск
сервиса из его каталога → `/health` → уборка за собой.

Почему так, а не `docker compose up --build`: рабочей копии на сервере больше нет.
Разработка живёт на маке, сервис — на домашней рабочей станции, и серверный
`compose.yaml` намеренно без блока `build`: место запуска не знает, как собирать.
Собирает выкат — во временном каталоге, который сам же и убирает. Реестра образов у
проекта нет, а образ с CUDA-слоями весит столько, что гонять его через туннель дороже,
чем скопировать исходники (решение владельца 01.09.2026).

Первым делом печатается ШАПКА «что уезжает»: ветка, последний коммит, неотправленные
коммиты и состояние рабочей копии в выкатываемых путях. Уезжает рабочая копия как есть,
а не коммит, поэтому грязное дерево — факт выката, а не деталь: по SHA потом не
восстановить, что именно собрано на сервере.

ПРЕФЛАЙТ идёт до подмены живого compose и до сборки: серверный `.env` на месте, buildkit
на сервере есть, и доставленный `compose.yaml` разворачивается `docker compose config`
с этим `.env`. Красный префлайт останавливает выкат, не тронув живой контейнер, — это
штатное поведение, а не поломка. Так ловится, например, отсутствие `API_KEYS`, без
которого compose репы намеренно не разворачивается.

Чего выкат НЕ трогает ни при каких флагах: `.env` и `models/` в каталоге сервиса. В
`.env` лежат настройки конкретной машины (модель, cuda, HOST_UID/GID), в `models/` —
несколько гигабайт весов, которые незачем возить.

Per-machine доступ к серверу — **SSH-алиас** из `.claude/config.local.yaml`
(`skills.deploy.prod_ssh_alias`, резолвер — `.claude/lib/machine_config.py`, env-override
`$PROD_SSH_ALIAS`). Host/user/приватный ключ — в `~/.ssh/config` под этим алиасом.
Адресов, имён хостов и секретов в этом файле нет и быть не должно.

Запуск (script-mode, чтобы поднялись inline-зависимости; `uv run python …` их игнорирует):
    uv run .claude/skills/deploy/scripts/deploy-prod.py            # выкат
    uv run .claude/skills/deploy/scripts/deploy-prod.py --dry-run  # план, сервер не трогается
"""

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# --- резолвер per-machine конфига (.claude/lib/machine_config.py) ---
# deploy-prod.py: .claude/skills/deploy/scripts/deploy-prod.py → parents[3] = .claude
_CLAUDE_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_CLAUDE_DIR / "lib"))
import machine_config  # noqa: E402

# --- Проектные константы (несекретные; per-machine ssh-алиас — в config.local.yaml) ---
# Пути даны относительно домашнего каталога на сервере: rsync так и адресует, а ssh-командам
# добавляется `~/`. Абсолютных путей с именем пользователя здесь нет намеренно.
REMOTE_DIR = "docker/voice-recognition"  # где сервис живёт и откуда поднимается
BUILD_DIR = ".cache/deploy/voice-recognition"  # временный каталог сборки, убирается за собой
IMAGE = "voice-recognition:latest"  # тег, который ждёт серверный compose
CONTAINER = "voice-recognition"  # имя контейнера (container_name в compose)
COMPOSE_LOCAL = "docker-compose.yml"  # источник правды о серверном compose — репа
COMPOSE_REMOTE = "compose.yaml"  # как файл называется на сервере
HEALTH_URL = "http://localhost:8000/health"  # снаружи порт открыт не всем, localhost — всегда

# Состав выката: ровно то, что нужно образу по `.dockerignore`. Возить репу целиком незачем —
# тесты, документация и сам compose в образ не попадают.
SOURCES: tuple[str, ...] = (
    "Dockerfile",
    ".dockerignore",
    "pyproject.toml",
    "uv.lock",
    "README.md",
    # без завершающего слэша: `src/` в rsync означает «содержимое каталога», и на сервер
    # уехали бы `api/`, `client/`, `transcription/` россыпью, а `COPY src /app/src` в
    # Dockerfile не нашёл бы каталога.
    "src",
)
# Пути, по которым считается грязность рабочей копии: ровно то, что уезжает, плюс compose,
# которым владеет репа. Правки в `.claude/`, тестах и README-соседях на сервер не едут.
DEPLOYED_PATHS: tuple[str, ...] = (*SOURCES, COMPOSE_LOCAL)

# Сколько ждать, пока контейнер станет healthy. В compose `start_period: 120s` — модель
# large-v3 грузится в GPU не мгновенно, и первые полторы минуты статус штатно `starting`.
HEALTH_TIMEOUT_S = 300
HEALTH_POLL_S = 5
# Сколько каталогов показывать в разбивке грязного дерева.
DIRTY_GROUPS_SHOWN = 8

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
DIM = "\033[2m"
RED = "\033[0;31m"
NC = "\033[0m"


def log(color: str, message: str) -> None:
    print(f"{color}{message}{NC}", flush=True)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"→ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, check=True, **kwargs)


def plural(count: int, one: str, few: str, many: str) -> str:
    """Русское склонение по числу. Числа здесь — сама грамматика, а не магические константы."""
    tail, hundred = count % 10, count % 100
    if tail == 1 and hundred != 11:  # noqa: PLR2004
        return one
    if 2 <= tail <= 4 and not 12 <= hundred <= 14:  # noqa: PLR2004
        return few
    return many


# --- Шапка «что уезжает» -------------------------------------------------------------


@dataclass(frozen=True)
class Change:
    kind: str
    path: str


@dataclass(frozen=True)
class WorkingCopy:
    """Снимок того, что уедет на сервер: git-координаты плюс расхождение с ними на диске."""

    branch: str
    commit: str
    unpushed: int | None  # None — у ветки нет upstream, сравнивать не с чем
    changes: tuple[Change, ...]
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


def read_working_copy() -> WorkingCopy:
    branch = git_output("rev-parse", "--abbrev-ref", "HEAD")
    commit = git_output("log", "-1", "--format=%h %ad %s", "--date=format:%d.%m.%Y %H:%M")
    status = git_output("status", "--porcelain", "-uall", "--", *DEPLOYED_PATHS)
    if branch is None or commit is None or status is None:
        return WorkingCopy("?", "?", None, (), readable=False)
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
        readable=True,
    )


def print_working_copy(state: WorkingCopy) -> None:
    """Печатается всегда и первой — до префлайта и до любого обращения к серверу."""
    log(YELLOW, "Что уезжает на сервер:")
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
        print(f"  дерево  {GREEN}чистое{NC} — на сервере соберётся ровно этот коммит", flush=True)
        return

    total = len(state.changes)
    files = plural(total, "изменение", "изменения", "изменений")
    print(f"  дерево  {RED}ГРЯЗНОЕ{NC}: {total} {files} в выкатываемых путях", flush=True)
    print(f"          {DIM}{', '.join(DEPLOYED_PATHS)}{NC}", flush=True)
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
    print(f"  {RED}соберётся не коммит {revision}, а рабочая копия как есть{NC}", flush=True)


# --- Работа на сервере ---------------------------------------------------------------


class PreflightError(RuntimeError):
    """Префлайт красный — выкат остановлен, живой контейнер и его compose не тронуты."""


def ssh(alias: str, command: str, **kwargs) -> subprocess.CompletedProcess:
    """Одна команда на сервере. BatchMode намеренно не выставляется: заход требует касания
    аппаратного ключа, и с BatchMode ssh просто упал бы. Касание одно на весь прогон —
    у алиаса включён ControlMaster с ControlPersist."""
    return run(["ssh", alias, command], **kwargs)


def ssh_capture(alias: str, command: str) -> subprocess.CompletedProcess:
    print(f"→ ssh {alias} {command}", flush=True)
    return subprocess.run(["ssh", alias, command], capture_output=True, text=True, check=False)


def sync_sources(alias: str) -> None:
    """Исходники и compose-файл — во временный каталог сборки. Живой каталог сервиса не трогается.

    `--delete` обязателен: каталог сборки переживает упавший выкат, и файл, удалённый в репе,
    иначе остался бы в образе.
    """
    run(
        [
            "rsync",
            "-az",
            "--delete",
            "-e",
            "ssh",
            "--rsync-path",
            f"mkdir -p {BUILD_DIR} && rsync",
            *SOURCES,
            f"{alias}:{BUILD_DIR}/",
        ]
    )
    # compose кладётся в тот же каталог под серверным именем: сначала его проверяет префлайт,
    # и только проверенный файл уезжает в живой каталог.
    run(["rsync", "-az", "-e", "ssh", COMPOSE_LOCAL, f"{alias}:{BUILD_DIR}/{COMPOSE_REMOTE}"])


def preflight(alias: str) -> None:
    """Барьер до подмены живого compose: `.env` на месте, buildkit есть, compose разворачивается.

    Красная стадия останавливает выкат в состоянии, когда на сервере изменён только временный
    каталог сборки: живой `compose.yaml` прежний, контейнер работает, `.env` и `models/` не тронуты.
    """
    env_file = f"~/{REMOTE_DIR}/.env"
    result = ssh_capture(alias, f"test -f {env_file}")
    if result.returncode != 0:
        raise PreflightError(
            f"на сервере нет {env_file} — выкату неоткуда взять настройки машины.\n"
            "  Живой контейнер не тронут. Заведи .env на сервере и запусти выкат заново."
        )

    result = ssh_capture(alias, "docker buildx version")
    if result.returncode != 0:
        raise PreflightError(
            "на сервере недоступен buildx (BuildKit).\n"
            "  Dockerfile объявляет `# syntax=docker/dockerfile:1.7` и использует cache-mount'ы:\n"
            "  без BuildKit сборка либо упадёт, либо каждый раз потянет CUDA-пакеты заново.\n"
            "  Живой контейнер не тронут."
        )

    result = ssh_capture(
        alias,
        f"cd ~/{BUILD_DIR} && docker compose --env-file {env_file} -f {COMPOSE_REMOTE} config -q",
    )
    if result.returncode != 0:
        raise PreflightError(
            "доставленный compose не разворачивается с серверным .env "
            f"(docker compose config, код {result.returncode}):\n"
            + "\n".join(f"    {line}" for line in result.stderr.strip().splitlines()[:10])
            + "\n  Живой контейнер и его compose.yaml не тронуты — на сервере изменён только"
            f"\n  временный каталог ~/{BUILD_DIR}."
            "\n  Обычная причина: в серверном .env не хватает переменной, которую compose репы"
            "\n  объявил обязательной. Допиши её в .env на сервере и запусти выкат заново."
        )


def build_image(alias: str) -> None:
    """Сборка образа на сервере из скопированных исходников.

    `DOCKER_BUILDKIT=1` выставляется явно: на старых демонах classic-строитель молча
    проигнорировал бы `# syntax=` и споткнулся о cache-mount'ы.
    """
    ssh(alias, f"cd ~/{BUILD_DIR} && DOCKER_BUILDKIT=1 docker build -t {IMAGE} .")


def install_compose(alias: str) -> None:
    """Проверенный compose — в живой каталог сервиса. `.env` и `models/` рядом не трогаются."""
    ssh(alias, f"cp ~/{BUILD_DIR}/{COMPOSE_REMOTE} ~/{REMOTE_DIR}/{COMPOSE_REMOTE}")


def compose_up(alias: str) -> None:
    """Перезапуск сервиса из его каталога. `--build` не нужен: образ уже собран выше."""
    ssh(alias, f"cd ~/{REMOTE_DIR} && docker compose up -d")


def wait_healthy(alias: str) -> None:
    """Ждём, пока докеровский healthcheck перестанет говорить `starting`."""
    log(YELLOW, f"Ждём healthy (до {HEALTH_TIMEOUT_S}s)...")
    deadline = time.monotonic() + HEALTH_TIMEOUT_S
    last = "?"
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["ssh", alias, f"docker inspect --format '{{{{.State.Health.Status}}}}' {CONTAINER}"],
            capture_output=True,
            text=True,
            check=False,
        )
        last = result.stdout.strip() or "нет контейнера"
        if last == "healthy":
            log(DIM, "  ✓ healthy")
            return
        if last == "unhealthy":
            break
        print(f"  {DIM}{last} — ждём {HEALTH_POLL_S}s{NC}", flush=True)
        time.sleep(HEALTH_POLL_S)
    ssh_capture(alias, f"cd ~/{REMOTE_DIR} && docker compose logs --tail 50")
    raise RuntimeError(f"контейнер {CONTAINER} не стал healthy (последний статус: {last})")


def check_health(alias: str) -> dict:
    """`/health` дёргается с самого сервера: снаружи порт опубликован не для всех сетей,
    а localhost открыт всегда."""
    result = ssh_capture(alias, f"curl -sf {HEALTH_URL}")
    if result.returncode != 0:
        raise RuntimeError(f"{HEALTH_URL} не ответил (curl, код {result.returncode})")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"{HEALTH_URL} ответил не JSON: {result.stdout[:200]!r}") from e
    if not payload.get("loaded"):
        raise RuntimeError(f"модель не загружена: {payload}")
    return payload


def cleanup(alias: str) -> None:
    """Уборка временного каталога сборки. Делается только после успеха: после упавшего выката
    каталог остаётся — по нему разбирают, что именно уехало."""
    ssh(alias, f"rm -rf ~/{BUILD_DIR}")


# --- Точка входа ---------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="deploy-prod.py",
        description="Выкат voice_recognition: исходники на сервер, сборка там, перезапуск.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="показать план и выйти, сервер не трогая"
    )
    return parser.parse_args(argv)


def print_plan(alias: str) -> None:
    print("[DRY RUN] Would execute the following steps:")
    print(f"  ssh alias: {alias}   сборка: ~/{BUILD_DIR}   сервис: ~/{REMOTE_DIR}")
    print(f"  1. rsync {' '.join(SOURCES)} -> {alias}:{BUILD_DIR}/ (--delete)")
    print(f"     rsync {COMPOSE_LOCAL} -> {alias}:{BUILD_DIR}/{COMPOSE_REMOTE}")
    print("  2. preflight (живой compose и контейнер ещё не тронуты):")
    print(f"     test -f ~/{REMOTE_DIR}/.env")
    print("     docker buildx version")
    print(
        f"     cd ~/{BUILD_DIR} && docker compose --env-file ~/{REMOTE_DIR}/.env"
        f" -f {COMPOSE_REMOTE} config -q"
    )
    print(f"  3. cd ~/{BUILD_DIR} && DOCKER_BUILDKIT=1 docker build -t {IMAGE} .")
    print(f"  4. cp ~/{BUILD_DIR}/{COMPOSE_REMOTE} -> ~/{REMOTE_DIR}/{COMPOSE_REMOTE}")
    print(f"  5. cd ~/{REMOTE_DIR} && docker compose up -d")
    print(
        f"  6. ждать healthy (до {HEALTH_TIMEOUT_S}s), затем curl -sf {HEALTH_URL} → loaded: true"
    )
    print(f"  7. rm -rf ~/{BUILD_DIR}")
    print(f"  {DIM}не трогается ни на одном шаге: ~/{REMOTE_DIR}/.env и ~/{REMOTE_DIR}/models/{NC}")


def main() -> None:
    args = parse_args(sys.argv[1:])

    os.chdir(machine_config.repo_root())

    alias = machine_config.skill_value("deploy", "prod_ssh_alias", env="PROD_SSH_ALIAS")

    print_working_copy(read_working_copy())

    if args.dry_run:
        print_plan(alias)
        return

    started = time.monotonic()
    log(YELLOW, f"\nВыкат идёт алиасом {alias} (адрес — в ~/.ssh/config)")

    try:
        log(YELLOW, "\n1/6 Копирую исходники в каталог сборки...")
        sync_sources(alias)

        log(YELLOW, "\n2/6 Префлайт...")
        preflight(alias)
        log(DIM, "  ✓ .env на месте, buildkit есть, compose разворачивается")

        log(YELLOW, "\n3/6 Собираю образ на сервере...")
        build_image(alias)

        log(YELLOW, "\n4/6 Кладу проверенный compose в каталог сервиса и поднимаю...")
        install_compose(alias)
        compose_up(alias)

        log(YELLOW, "\n5/6 Проверяю сервис...")
        wait_healthy(alias)
        payload = check_health(alias)
        print(f"  {GREEN}/health{NC}: {json.dumps(payload, ensure_ascii=False)}", flush=True)
    except PreflightError, RuntimeError, subprocess.CalledProcessError:
        log(RED, f"\nКаталог сборки ~/{BUILD_DIR} оставлен на сервере — по нему видно, что уехало.")
        log(RED, f"Убрать вручную: ssh {alias} 'rm -rf ~/{BUILD_DIR}'")
        raise

    log(YELLOW, "\n6/6 Убираю каталог сборки...")
    cleanup(alias)

    log(GREEN, f"\nВыкат завершён за {time.monotonic() - started:.1f}s.")


if __name__ == "__main__":
    try:
        main()
    except machine_config.ConfigError as e:
        sys.exit(str(e))
    except PreflightError as e:
        log(RED, f"\nВыкат остановлен префлайтом: {e}")
        sys.exit(2)
    except RuntimeError as e:
        log(RED, f"\nВыкат не дошёл до конца: {e}")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        log(RED, f"Команда завершилась с кодом {e.returncode}")
        sys.exit(e.returncode)
