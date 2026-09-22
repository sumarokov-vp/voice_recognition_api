"""Команды на целевой машине по ssh-алиасу."""

from __future__ import annotations

import shlex
import subprocess
from typing import Any

from deploy_console import DIM, NC, run


class RemoteShell:
    """Одна команда на целевой машине.

    BatchMode намеренно не выставляется: заход на обе машины требует касания аппаратного
    ключа, и с BatchMode ssh просто упал бы. Касание одно на весь прогон — у алиасов включён
    ControlMaster с ControlPersist.

    `wrap_in_bash` — про login shell на той стороне. Команды выката написаны на POSIX sh
    (`VAR=… cmd`, `&&`, `$?`), а на Mac mini login shell — fish, которая присваивание перед
    командой не понимает. Там команда уезжает завёрнутой в `bash -c`. На домашнем сервере
    login shell и так bash: заворачивать нечего, и проверенный годами выкат остаётся
    посимвольно прежним.
    """

    def __init__(self, alias: str, *, wrap_in_bash: bool = False) -> None:
        self.alias = alias
        self._wrap_in_bash = wrap_in_bash

    def argv(self, command: str) -> list[str]:
        if self._wrap_in_bash:
            return ["ssh", self.alias, "bash", "-c", shlex.quote(command)]
        return ["ssh", self.alias, command]

    def run(self, command: str, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        """Команда с трассировкой и `check=True` — вывод идёт прямо в терминал."""
        return run(self.argv(command), **kwargs)

    def capture(self, command: str, *, quiet: bool = False) -> subprocess.CompletedProcess[str]:
        """Команда, вывод и код возврата которой разбирает сам выкат.

        `quiet` — для опроса в цикле: иначе каждые несколько секунд печаталась бы одна и та же
        строка трассировки.
        """
        if not quiet:
            print(f"→ {' '.join(self.argv(command))}", flush=True)
        return subprocess.run(
            self.argv(command), capture_output=True, text=True, check=False
        )

    def run_with_secret_stdin(
        self, command: str, secret: str
    ) -> subprocess.CompletedProcess[str]:
        """Команда, которой секрет уезжает в stdin.

        Именно в stdin, а не в аргументы: аргументы видны в `ps` на той стороне и оседают в
        истории шелла. Печатается только сама команда.
        """
        print(f"→ {' '.join(self.argv(command))}   {DIM}(секрет — в stdin){NC}", flush=True)
        return subprocess.run(
            self.argv(command),
            input=secret,
            capture_output=True,
            text=True,
            check=False,
        )
