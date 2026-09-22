# /// script
# requires-python = ">=3.14"  # `except A, B:` без скобок — PEP 758, только 3.14+
# dependencies = ["pyyaml"]
# ///
"""Выкат voice_recognition. Целей две, и обе боевые.

    --target home   домашний Linux-сервер: faster-whisper на CUDA, сервис в docker.
                    Цель по умолчанию — прежняя однокомандная выкатка, без изменений.
    --target mini   Mac mini: mlx-whisper на Metal, сервис нативный, под launchd.

Две цели, а не два скрипта, потому что общее у них ровно то, что важно человеку: одна и та же
рабочая копия уезжает по одной команде и считается доехавшей по одному признаку — `/health`
с `loaded: true`. Шапка «что уезжает» и разбор падения тоже общие. Различие целиком в способе
доставки (образ против исходников) и спрятано в самой цели; здесь виден только выбор.

Сервис на домашнем сервере продолжает работать: mini его не заменяет и не отменяет.
Потребители переводятся по одному, и до тех пор выкатывать надо обе машины.

Первым делом печатается ШАПКА «что уезжает»: ветка, последний коммит, неотправленные коммиты
и состояние рабочей копии в тех путях, которые уезжают на выбранную цель. Уезжает рабочая
копия как есть, а не коммит, поэтому грязное дерево — факт выката, а не деталь: по SHA потом
не восстановить, что именно уехало.

ПРЕФЛАЙТ есть у обеих целей, но стоит на разном месте: на домашнем сервере — после доставки
исходников во временный каталог сборки (живого сервиса она не касается), на mini — до
доставки (там исходники ложатся прямо в рабочую копию сервиса). Красный префлайт — штатная
остановка, а не поломка: живой сервис остаётся на прежнем коде.

Чего выкат НЕ трогает ни при каких флагах и ни на одной цели: `.env` (настройки машины),
веса моделей (`models/` на домашнем сервере, кеш Hugging Face на mini), а на mini ещё и
`.venv` целиком (только доустанавливает в него зависимости) и plist демона — его кладёт
pyinfra.

Per-machine доступ — из `.claude/config.local.yaml` (резолвер `.claude/lib/machine_config.py`):
`skills.deploy.prod_ssh_alias` для домашнего сервера, `skills.deploy.mini_ssh_alias` и
`skills.deploy.mini_sudo_pass_entry` для mini. Адресов, имён хостов и секретов в этом файле
нет и быть не должно: ssh-алиасы раскрываются в `~/.ssh/config`, sudo-пароль лежит в `pass`
и читается здесь, на машине разработчика, — на самой mini ни pass, ни gpg нет.

Запуск (script-mode, чтобы поднялись inline-зависимости; `uv run python …` их игнорирует):
    uv run .claude/skills/deploy/scripts/deploy-prod.py                  # домашний сервер
    uv run .claude/skills/deploy/scripts/deploy-prod.py --target mini    # Mac mini
    uv run .claude/skills/deploy/scripts/deploy-prod.py --target mini --dry-run   # только план
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# --- резолвер per-machine конфига (.claude/lib/machine_config.py) ---
# deploy-prod.py: .claude/skills/deploy/scripts/deploy-prod.py → parents[3] = .claude
_CLAUDE_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_CLAUDE_DIR / "lib"))
import machine_config  # noqa: E402
from deploy_console import GREEN, RED, YELLOW, PreflightError, log  # noqa: E402
from deploy_home_docker import HomeDockerTarget  # noqa: E402
from deploy_mini_native import MiniNativeTarget  # noqa: E402
from deploy_remote_shell import RemoteShell  # noqa: E402
from deploy_working_copy import print_working_copy, read_working_copy  # noqa: E402
from i_deploy_target import IDeployTarget  # noqa: E402

HOME = "home"
MINI = "mini"


def build_home_target() -> IDeployTarget:
    alias = machine_config.skill_value("deploy", "prod_ssh_alias", env="PROD_SSH_ALIAS")
    return HomeDockerTarget(RemoteShell(alias))


def build_mini_target() -> IDeployTarget:
    alias = machine_config.skill_value("deploy", "mini_ssh_alias", env="MINI_SSH_ALIAS")
    pass_entry = machine_config.skill_value(
        "deploy", "mini_sudo_pass_entry", env="MINI_SUDO_PASS_ENTRY"
    )
    return MiniNativeTarget(
        # login shell на mini — fish, а команды выката написаны на POSIX sh.
        RemoteShell(alias, wrap_in_bash=True),
        sudo_pass_entry=pass_entry,
        # Пароль читается не здесь, а в префлайте — чтобы `--dry-run` не дёргал gpg-агента.
        read_sudo_password=lambda: machine_config.read_pass_entry(pass_entry)[0],
    )


def build_target(name: str) -> IDeployTarget:
    return build_home_target() if name == HOME else build_mini_target()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="deploy-prod.py",
        description="Выкат voice_recognition: домашний сервер (docker) или Mac mini (нативно).",
    )
    parser.add_argument(
        "--target",
        choices=(HOME, MINI),
        default=HOME,
        help="куда выкатывать: home — домашний сервер в docker (по умолчанию),"
        " mini — Mac mini нативно под launchd",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="показать план и выйти, машину не трогая"
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])

    os.chdir(machine_config.repo_root())

    target = build_target(args.target)

    print_working_copy(read_working_copy(target.deployed_paths))

    if args.dry_run:
        print(f"[DRY RUN] Цель {target.name}: {target.summary}. Шаги выката:")
        target.print_plan()
        return

    started = time.monotonic()
    log(YELLOW, f"\nВыкат идёт на цель {target.name}: {target.summary}")

    try:
        target.run()
    except PreflightError, RuntimeError, subprocess.CalledProcessError:
        log(RED, f"\n{target.failure_hint()}")
        raise

    log(GREEN, f"\nВыкат на {target.name} завершён за {time.monotonic() - started:.1f}s.")


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
