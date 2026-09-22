"""Цель `mini` — Mac mini: исходники в живую рабочую копию → доустановка зависимостей в
`.venv` → перезапуск LaunchDaemon → `/health`.

ПОЧЕМУ БЕЗ DOCKER. Это ограничение платформы, а не вкус. GPU на macOS не пробрасывается ни в
одну Linux-VM — ни у colima, ни у Apple `container`; Metal доступен только нативному процессу
macOS. В контейнере `large-v3` считал бы на CPU со скоростью около 1x реального времени,
нативно на MLX turbo-модель даёт 3.9x. Поэтому здесь нет ни образа, ни compose, и
«унифицировать» выкат обратно в docker нельзя — унификация отняла бы GPU.

ПОЧЕМУ LaunchDaemon, а не LaunchAgent или `brew services`. Mac mini headless: графического
логина нет, домена `gui/<uid>` не существует, и `brew services` там падает с `Domain does not
support specified action`. Демон живёт в системном домене, поэтому перезапуск требует root.

Порядок стадий здесь обратный домашнему: префлайт идёт ДО доставки исходников. На домашнем
сервере исходники уезжают во временный каталог сборки и живого сервиса не касаются, а тут
они ложатся прямо в рабочую копию, из которой сервис и запускается. Пускать их туда, не
убедившись, что машина готова, нечем оправдать.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import StrEnum

from deploy_console import DIM, GREEN, NC, RED, YELLOW, PreflightError, echo_output, log, run
from deploy_health import wait_for_health
from deploy_remote_shell import RemoteShell

# Пути относительно домашнего каталога на mini: rsync так и адресует, а ssh-командам
# добавляется `~/`. Абсолютных путей с именем пользователя здесь нет намеренно.
REPO_DIR = "projects/voice_recognition"  # рабочая копия, из неё же работает сервис
VENV_PYTHON = ".venv/bin/python"  # интерпретатор сервиса, создан отдельно от выката
LOG_PATH = "Library/Logs/voice-recognition.log"  # куда пишет демон (StandardOutPath в plist)
DAEMON_LABEL = "com.sumarokov.voice-recognition"
DAEMON_TARGET = f"system/{DAEMON_LABEL}"  # системный домен: демон, не агент
EXTRAS = ".[server,mlx]"  # mlx ставится по маркеру платформы — на macOS/arm64 он и нужен
# В неинтерактивном bash PATH не содержит homebrew — ни uv, ни ffmpeg по имени не найдутся.
BREW_BIN = "/opt/homebrew/bin"

# Что уезжает: только то, из чего состоит запускаемый код. Dockerfile и compose тут ни при
# чём, `.env` и `.venv` — собственность машины.
SOURCE_TREE = "src"  # без завершающего слэша: уезжает сам каталог, а не его содержимое
SOURCE_FILES: tuple[str, ...] = ("pyproject.toml", "uv.lock", "README.md")

# Turbo-модель поднимается из кеша Hugging Face за десятки секунд; запас взят на холодный
# кеш, когда веса ещё качаются.
HEALTH_TIMEOUT_S = 300
HEALTH_POLL_S = 5

DEFAULT_API_PORT = "8000"
LOOPBACK = "127.0.0.1"
# Сервис слушает адрес WireGuard, а не wildcard, — но если в `.env` окажется wildcard,
# спрашивать надо всё равно с самой машины, по loopback.
WILDCARD_HOSTS = frozenset({"", "0.0.0.0", "::", "*"})

ReadSecret = Callable[[], str]


class Stage(StrEnum):
    """До какого места дошёл выкат — от этого зависит, что осталось на машине."""

    PREFLIGHT = "префлайт"
    SOURCES_DELIVERED = "исходники доставлены"
    RESTARTED = "демон перезапущен"


def parse_env_values(text: str) -> dict[str, str]:
    """Строки вида `KEY=value` из `.env` в словарь. Кавычки вокруг значения снимаются."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def parse_daemon_pid(text: str) -> int | None:
    """Pid из вывода `launchctl print`: строка вида `	pid = 317`. None — процесса нет."""
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "pid" and value.strip().isdigit():
            return int(value.strip())
    return None


def health_url(values: dict[str, str]) -> str:
    """Адрес `/health` по настройкам машины.

    Сервис на mini слушает адрес WireGuard `API_HOST`, а не loopback и не wildcard: из mesh и
    из контейнеров самой mini он виден, а в чужой сети (отель, кафе) порт не появляется
    вовсе. Поэтому проверять его надо ровно по тому адресу, который он занял, — адрес берётся
    из `.env` на машине, а не зашит сюда.
    """
    host = values.get("API_HOST", "")
    port = values.get("API_PORT", DEFAULT_API_PORT)
    if host in WILDCARD_HOSTS:
        host = LOOPBACK
    elif ":" in host:  # IPv6-литерал в URL берётся в скобки
        host = f"[{host}]"
    return f"http://{host}:{port}/health"


class MiniNativeTarget:
    """Выкат нативного сервиса на Mac mini.

    Секрет (sudo-пароль) сюда не передаётся значением: цель знает лишь путь к записи `pass`
    (чтобы назвать его в плане и в ошибках) и функцию, которая читает пароль в момент, когда
    он понадобился. Где лежит хранилище и как оно устроено — забота точки входа.
    """

    def __init__(
        self,
        shell: RemoteShell,
        *,
        sudo_pass_entry: str,
        read_sudo_password: ReadSecret,
    ) -> None:
        self._shell = shell
        self._sudo_pass_entry = sudo_pass_entry
        self._read_sudo_password = read_sudo_password
        self._stage = Stage.PREFLIGHT

    @property
    def name(self) -> str:
        return "mini"

    @property
    def summary(self) -> str:
        return f"нативный сервис на {self._shell.alias} (mlx-whisper на Metal, вне docker)"

    @property
    def deployed_paths(self) -> tuple[str, ...]:
        return (SOURCE_TREE, *SOURCE_FILES)

    def failure_hint(self) -> str:
        if self._stage is Stage.PREFLIGHT:
            return (
                "На mini не изменилось ничего: исходники не уезжали, зависимости не ставились,"
                "\nдемон работает на прежнем коде."
            )
        if self._stage is Stage.SOURCES_DELIVERED:
            return (
                f"На mini уже лежат новые исходники (~/{REPO_DIR}), но демон НЕ перезапускался"
                "\nи продолжает работать на прежнем коде. Почини локально и запусти выкат"
                " заново."
            )
        return (
            f"Демон перезапущен на новом коде и мог не подняться. Лог:"
            f"\n  ssh {self._shell.alias} 'tail -n 50 ~/{LOG_PATH}'"
            "\nПочини локально и запусти выкат заново — правкой на месте чинить нечего:"
            "\nрабочая копия на mini перезаписывается выкатом."
        )

    def print_plan(self) -> None:
        alias = self._shell.alias
        print(f"  ssh alias: {alias}   рабочая копия и сервис: ~/{REPO_DIR}")
        print("  1. preflight (исходники ещё не уезжали, демон работает на прежнем коде):")
        print(f"     test -f ~/{REPO_DIR}/pyproject.toml   test -f ~/{REPO_DIR}/.env")
        print(f"     test -x ~/{REPO_DIR}/{VENV_PYTHON}    launchctl print {DAEMON_TARGET}")
        print(f"     command -v uv (PATH += {BREW_BIN})")
        print(f"     адрес проверки — из API_HOST/API_PORT в ~/{REPO_DIR}/.env")
        print(f"     sudo-пароль — из pass: {self._sudo_pass_entry}")
        print(f"  2. rsync {SOURCE_TREE} -> {alias}:{REPO_DIR}/ (--delete внутри src/)")
        print(f"     rsync {' '.join(SOURCE_FILES)} -> {alias}:{REPO_DIR}/")
        print(f"  3. cd ~/{REPO_DIR} && uv pip install --python {VENV_PYTHON} -e '{EXTRAS}'")
        print(f"  4. sudo launchctl kickstart -k {DAEMON_TARGET}   (пароль уходит в stdin)")
        print("     + сверка pid демона до и после: процесс обязан смениться")
        print(f"  5. ждать /health → loaded: true (до {HEALTH_TIMEOUT_S}s)")
        print(
            f"  {DIM}не трогается ни на одном шаге: ~/{REPO_DIR}/.env, сам ~/{REPO_DIR}/.venv"
            f"\n  (только доустановка пакетов), plist демона и кеш весов ~/.cache/huggingface{NC}"
        )

    def run(self) -> None:
        log(YELLOW, "\n1/5 Префлайт (исходники ещё не уезжали)...")
        self._check_machine_ready()
        url = self._read_health_url()
        sudo_password = self._read_sudo_password()
        pid_before = self._read_daemon_pid()
        log(DIM, f"  ✓ рабочая копия, .env, .venv, демон и uv на месте; проверка пойдёт на {url}")

        log(YELLOW, "\n2/5 Копирую исходники в рабочую копию...")
        self._sync_sources()
        self._stage = Stage.SOURCES_DELIVERED

        log(YELLOW, "\n3/5 Доустанавливаю зависимости в .venv...")
        self._install_dependencies()

        log(YELLOW, "\n4/5 Перезапускаю демон...")
        self._kickstart(sudo_password)
        self._stage = Stage.RESTARTED
        self._check_process_replaced(pid_before)

        log(YELLOW, "\n5/5 Проверяю сервис...")
        outcome = wait_for_health(
            self._shell, url, timeout_s=HEALTH_TIMEOUT_S, poll_s=HEALTH_POLL_S
        )
        if not outcome.ok:
            self._print_recent_logs()
            raise RuntimeError(outcome.reason)
        body = json.dumps(outcome.payload, ensure_ascii=False)
        print(f"  {GREEN}/health{NC}: {body}", flush=True)

    # --- шаги -----------------------------------------------------------------------

    def _check_machine_ready(self) -> None:
        """Барьер до доставки исходников: всё, что выкат не создаёт, обязано быть на месте.

        Рабочую копию, `.env`, `.venv` и plist демона ставит не выкат: `.venv` собирают руками
        (`uv venv` + установка), plist раскладывает pyinfra. Выкат их чинить не умеет и
        намеренно не пытается — молча создать их значило бы поднять сервис с чужими
        настройками.
        """
        checks = (
            (
                f"test -f ~/{REPO_DIR}/pyproject.toml",
                f"на mini нет рабочей копии ~/{REPO_DIR} — выкату некуда класть исходники.",
            ),
            (
                f"test -f ~/{REPO_DIR}/.env",
                f"на mini нет ~/{REPO_DIR}/.env — выкату неоткуда взять настройки машины"
                " (движок, адрес, ключи).",
            ),
            (
                f"test -x ~/{REPO_DIR}/{VENV_PYTHON}",
                f"на mini нет ~/{REPO_DIR}/{VENV_PYTHON} — окружение сервиса собирается"
                " отдельно (uv venv на Python 3.14), выкат его не создаёт.",
            ),
            (
                f"launchctl print {DAEMON_TARGET} > /dev/null",
                f"демон {DAEMON_TARGET} не загружен — перезапускать нечего."
                "\n  Plist кладёт pyinfra, а не выкат.",
            ),
            (
                f"PATH={BREW_BIN}:$PATH command -v uv > /dev/null",
                "на mini не нашёлся uv — им ставятся зависимости в .venv."
                f"\n  Проверь, что он есть в {BREW_BIN}.",
            ),
        )
        for command, complaint in checks:
            if self._shell.capture(command).returncode != 0:
                raise PreflightError(f"{complaint}\n  Сервис на mini не тронут.")

    def _read_health_url(self) -> str:
        result = self._shell.capture(f"grep -E '^(API_HOST|API_PORT)=' ~/{REPO_DIR}/.env")
        # grep с кодом 1 — это «строк нет», а не поломка: значения тогда берутся по умолчанию,
        # как их понимает сам сервис.
        return health_url(parse_env_values(result.stdout) if result.returncode == 0 else {})

    def _sync_sources(self) -> None:
        """Исходники — прямо в рабочую копию, из которой работает сервис.

        Два вызова, а не один, и это не лишний шаг. `--delete` в rsync стирает лишнее только
        внутри переданных каталогов, но полагаться на это в каталоге, где рядом лежат `.env`,
        `.venv` и `.git`, не стоит: первый вызов чистит ровно `src/` (удалённый в репе модуль
        обязан исчезнуть и здесь), второй кладёт отдельные файлы, ничего не удаляя.
        """
        alias = self._shell.alias
        run(["rsync", "-az", "--delete", "-e", "ssh", SOURCE_TREE, f"{alias}:{REPO_DIR}/"])
        run(["rsync", "-az", "-e", "ssh", *SOURCE_FILES, f"{alias}:{REPO_DIR}/"])

    def _install_dependencies(self) -> None:
        """Доустановка зависимостей в существующий `.venv`.

        Именно `uv pip install`, а не `uv sync`: sync приводит окружение к локфайлу целиком и
        выкинул бы из него всё, что поставлено помимо (движок mlx живёт под маркером
        платформы). Окружение переживает выкат, пересоздаётся только руками.
        """
        self._shell.run(
            f"cd ~/{REPO_DIR} && PATH={BREW_BIN}:$PATH"
            f" uv pip install --python {VENV_PYTHON} -e '{EXTRAS}'"
        )

    def _kickstart(self, sudo_password: str) -> None:
        """Перезапуск демона в системном домене — отсюда и root.

        Пароль уезжает в stdin `sudo -S`: в аргументах он был бы виден в `ps` на той стороне.
        На самой mini ни pass, ни gpg нет — запись читается здесь, на машине разработчика.
        """
        result = self._shell.run_with_secret_stdin(
            f'sudo -S -p "" launchctl kickstart -k {DAEMON_TARGET}',
            f"{sudo_password}\n",
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"перезапуск демона не удался (код {result.returncode}):"
                + "\n".join(f"\n    {line}" for line in result.stderr.strip().splitlines()[:10])
                + f"\n  Проверь sudo-пароль в pass ({self._sudo_pass_entry})."
                "\n  Демон остался на прежнем коде, но исходники в рабочей копии уже новые."
            )

    def _read_daemon_pid(self) -> int | None:
        """Pid демона по `launchctl print`. None — процесса сейчас нет (демон перезапускается
        или падает в цикле под KeepAlive)."""
        result = self._shell.capture(f"launchctl print {DAEMON_TARGET}", quiet=True)
        return parse_daemon_pid(result.stdout) if result.returncode == 0 else None

    def _check_process_replaced(self, pid_before: int | None) -> None:
        """Сверка pid до и после перезапуска.

        Без неё зелёный `/health` можно получить от старого процесса и решить, что новый код
        уехал, когда он всё ещё лежит рядом непрочитанным.
        """
        pid_after = self._read_daemon_pid()
        if pid_after is not None and pid_after == pid_before:
            raise RuntimeError(
                f"демон не перезапустился: pid прежний ({pid_before}). "
                f"Проверь: launchctl print {DAEMON_TARGET}"
            )
        log(DIM, f"  ✓ процесс сменился: pid {pid_before} → {pid_after or 'ещё поднимается'}")

    def _print_recent_logs(self) -> None:
        log(RED, "  последние строки лога демона:")
        echo_output(self._shell.capture(f"tail -n 50 ~/{LOG_PATH}"))
