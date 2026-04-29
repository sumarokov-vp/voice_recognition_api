---
name: deploy
description: Деплой voice_recognition через Docker Compose. Пересобирает образ и перезапускает контейнер.
allowed-tools: Bash(.claude/skills/deploy/scripts/deploy.sh)
---

Запусти деплой сервиса:

```bash
.claude/skills/deploy/scripts/deploy.sh
```

Скрипт сам пересобирает образ, ждёт healthcheck и проверяет `/health`.
Сообщи пользователю результат — успех или ошибку из вывода скрипта.
