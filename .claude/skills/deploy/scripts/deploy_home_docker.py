"""Цель `home` — домашний Linux-сервер: исходники туда → сборка образа ТАМ → перезапуск
контейнера из его каталога → `/health` → уборка за собой.

Движок здесь `faster-whisper` на CUDA, сервис живёт в docker. Эта цель обслуживает нынешних
потребителей (`voice_input` на макбуке ходит именно сюда) и гаситься не собирается: появление
Mac mini ничего из этого не отменяет.

Почему не `docker compose up --build`: рабочей копии на сервере нет. Разработка живёт на
маке, и серверный `compose.yaml` намеренно без блока `build` — место запуска не знает, как
собирать. Собирает выкат, во временном каталоге, который сам же и убирает. Реестра образов у
проекта нет, а образ с CUDA-слоями весит столько, что гонять его через туннель дороже, чем
скопировать исходники (решение владельца 01.09.2026).
"""

from __future__ import annotations

import json
import time

from deploy_console import DIM, GREEN, NC, RED, YELLOW, PreflightError, echo_output, log, run
from deploy_health import probe_health
from deploy_remote_shell import RemoteShell

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

# Сколько ждать, пока контейнер станет healthy. В compose `start_period: 120s` — модель
# large-v3 грузится в GPU не мгновенно, и первые полторы минуты статус штатно `starting`.
HEALTH_TIMEOUT_S = 300
HEALTH_POLL_S = 5


class HomeDockerTarget:
    """Выкат на домашний сервер: сборка образа на месте и перезапуск compose-сервиса."""

    def __init__(self, shell: RemoteShell) -> None:
        self._shell = shell

    @property
    def name(self) -> str:
        return "home"

    @property
    def summary(self) -> str:
        return f"docker-сервис на {self._shell.alias} (faster-whisper на CUDA)"

    @property
    def deployed_paths(self) -> tuple[str, ...]:
        # Плюс compose, которым владеет репа: он тоже уезжает и тоже бывает грязным.
        return (*SOURCES, COMPOSE_LOCAL)

    def failure_hint(self) -> str:
        return (
            f"Каталог сборки ~/{BUILD_DIR} оставлен на сервере — по нему видно, что уехало.\n"
            f"Убрать вручную: ssh {self._shell.alias} 'rm -rf ~/{BUILD_DIR}'"
        )

    def print_plan(self) -> None:
        alias = self._shell.alias
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
            f"  6. ждать healthy (до {HEALTH_TIMEOUT_S}s), затем curl -sf {HEALTH_URL}"
            " → loaded: true"
        )
        print(f"  7. rm -rf ~/{BUILD_DIR}")
        print(
            f"  {DIM}не трогается ни на одном шаге: ~/{REMOTE_DIR}/.env"
            f" и ~/{REMOTE_DIR}/models/{NC}"
        )

    def run(self) -> None:
        log(YELLOW, "\n1/6 Копирую исходники в каталог сборки...")
        self._sync_sources()

        log(YELLOW, "\n2/6 Префлайт...")
        self._preflight()
        log(DIM, "  ✓ .env на месте, buildkit есть, compose разворачивается")

        log(YELLOW, "\n3/6 Собираю образ на сервере...")
        self._build_image()

        log(YELLOW, "\n4/6 Кладу проверенный compose в каталог сервиса и поднимаю...")
        self._install_compose()
        self._compose_up()

        log(YELLOW, "\n5/6 Проверяю сервис...")
        self._wait_healthy()
        self._check_health()

        log(YELLOW, "\n6/6 Убираю каталог сборки...")
        self._cleanup()

    # --- шаги -----------------------------------------------------------------------

    def _sync_sources(self) -> None:
        """Исходники и compose — во временный каталог сборки. Живой каталог сервиса не трогается.

        `--delete` обязателен: каталог сборки переживает упавший выкат, и файл, удалённый в
        репе, иначе остался бы в образе.
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
                f"{self._shell.alias}:{BUILD_DIR}/",
            ]
        )
        # compose кладётся в тот же каталог под серверным именем: сначала его проверяет
        # префлайт, и только проверенный файл уезжает в живой каталог.
        run(
            [
                "rsync",
                "-az",
                "-e",
                "ssh",
                COMPOSE_LOCAL,
                f"{self._shell.alias}:{BUILD_DIR}/{COMPOSE_REMOTE}",
            ]
        )

    def _preflight(self) -> None:
        """Барьер до подмены живого compose: `.env` на месте, buildkit есть, compose
        разворачивается.

        Красная стадия останавливает выкат в состоянии, когда на сервере изменён только
        временный каталог сборки: живой `compose.yaml` прежний, контейнер работает, `.env` и
        `models/` не тронуты.
        """
        env_file = f"~/{REMOTE_DIR}/.env"
        result = self._shell.capture(f"test -f {env_file}")
        if result.returncode != 0:
            raise PreflightError(
                f"на сервере нет {env_file} — выкату неоткуда взять настройки машины.\n"
                "  Живой контейнер не тронут. Заведи .env на сервере и запусти выкат заново."
            )

        result = self._shell.capture("docker buildx version")
        if result.returncode != 0:
            raise PreflightError(
                "на сервере недоступен buildx (BuildKit).\n"
                "  Dockerfile объявляет `# syntax=docker/dockerfile:1.7` и использует"
                " cache-mount'ы:\n"
                "  без BuildKit сборка либо упадёт, либо каждый раз потянет CUDA-пакеты"
                " заново.\n"
                "  Живой контейнер не тронут."
            )

        result = self._shell.capture(
            f"cd ~/{BUILD_DIR} && docker compose --env-file {env_file}"
            f" -f {COMPOSE_REMOTE} config -q"
        )
        if result.returncode != 0:
            raise PreflightError(
                "доставленный compose не разворачивается с серверным .env "
                f"(docker compose config, код {result.returncode}):\n"
                + "\n".join(f"    {line}" for line in result.stderr.strip().splitlines()[:10])
                + "\n  Живой контейнер и его compose.yaml не тронуты — на сервере изменён только"
                f"\n  временный каталог ~/{BUILD_DIR}."
                "\n  Обычная причина: в серверном .env не хватает переменной, которую compose"
                "\n  репы объявил обязательной. Допиши её в .env на сервере и запусти выкат"
                " заново."
            )

    def _build_image(self) -> None:
        """Сборка образа на сервере из скопированных исходников.

        `DOCKER_BUILDKIT=1` выставляется явно: на старых демонах classic-строитель молча
        проигнорировал бы `# syntax=` и споткнулся о cache-mount'ы.
        """
        self._shell.run(f"cd ~/{BUILD_DIR} && DOCKER_BUILDKIT=1 docker build -t {IMAGE} .")

    def _install_compose(self) -> None:
        """Проверенный compose — в живой каталог сервиса. `.env` и `models/` рядом не трогаются."""
        self._shell.run(f"cp ~/{BUILD_DIR}/{COMPOSE_REMOTE} ~/{REMOTE_DIR}/{COMPOSE_REMOTE}")

    def _compose_up(self) -> None:
        """Перезапуск сервиса из его каталога. `--build` не нужен: образ уже собран выше."""
        self._shell.run(f"cd ~/{REMOTE_DIR} && docker compose up -d")

    def _wait_healthy(self) -> None:
        """Ждём, пока докеровский healthcheck перестанет говорить `starting`."""
        log(YELLOW, f"Ждём healthy (до {HEALTH_TIMEOUT_S}s)...")
        deadline = time.monotonic() + HEALTH_TIMEOUT_S
        last = "?"
        while time.monotonic() < deadline:
            result = self._shell.capture(
                f"docker inspect --format '{{{{.State.Health.Status}}}}' {CONTAINER}", quiet=True
            )
            last = result.stdout.strip() or "нет контейнера"
            if last == "healthy":
                log(DIM, "  ✓ healthy")
                return
            if last == "unhealthy":
                break
            print(f"  {DIM}{last} — ждём {HEALTH_POLL_S}s{NC}", flush=True)
            time.sleep(HEALTH_POLL_S)
        self._print_recent_logs()
        raise RuntimeError(f"контейнер {CONTAINER} не стал healthy (последний статус: {last})")

    def _check_health(self) -> None:
        outcome = probe_health(self._shell, HEALTH_URL)
        if not outcome.ok:
            self._print_recent_logs()
            raise RuntimeError(outcome.reason)
        body = json.dumps(outcome.payload, ensure_ascii=False)
        print(f"  {GREEN}/health{NC}: {body}", flush=True)

    def _print_recent_logs(self) -> None:
        log(RED, "  последние строки лога контейнера:")
        echo_output(self._shell.capture(f"cd ~/{REMOTE_DIR} && docker compose logs --tail 50"))

    def _cleanup(self) -> None:
        """Уборка временного каталога сборки. Делается только после успеха: после упавшего
        выката каталог остаётся — по нему разбирают, что именно уехало."""
        self._shell.run(f"rm -rf ~/{BUILD_DIR}")
