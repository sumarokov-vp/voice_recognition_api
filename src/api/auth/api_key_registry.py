import secrets
from collections.abc import Mapping
from types import MappingProxyType

PAIR_SEPARATOR = ","
NAME_SEPARATOR = ":"


class ApiKeysFormatError(ValueError):
    """Переменная API_KEYS задана в неверном формате."""


class ApiKeyRegistry:
    """Ключи потребителей: по предъявленному ключу называет имя потребителя."""

    def __init__(self, keys_by_consumer: Mapping[str, str]) -> None:
        self._keys_by_consumer: Mapping[str, str] = MappingProxyType(dict(keys_by_consumer))

    @classmethod
    def parse(cls, raw: str) -> ApiKeyRegistry:
        """Разобрать строку вида `имя:ключ,имя:ключ`.

        Пустая строка — ошибка, а не «пускаем всех»: молча открытый сервис хуже упавшего.
        """
        pairs = [chunk.strip() for chunk in raw.split(PAIR_SEPARATOR)]
        meaningful = [chunk for chunk in pairs if chunk]
        if not meaningful:
            raise ApiKeysFormatError(
                "API_KEYS пуст: сервис без ключей не запускается. "
                f"Ожидается `имя{NAME_SEPARATOR}ключ`, пары через `{PAIR_SEPARATOR}`.",
            )

        keys_by_consumer: dict[str, str] = {}
        for chunk in meaningful:
            name, separator, key = chunk.partition(NAME_SEPARATOR)
            name = name.strip()
            key = key.strip()
            if not separator or not name or not key:
                raise ApiKeysFormatError(
                    f"Пара `{chunk}` не похожа на `имя{NAME_SEPARATOR}ключ`.",
                )
            if name in keys_by_consumer:
                raise ApiKeysFormatError(f"Потребитель `{name}` указан в API_KEYS дважды.")
            keys_by_consumer[name] = key
        return cls(keys_by_consumer)

    def consumer_for(self, key: str) -> str | None:
        """Вернуть имя потребителя по ключу или None, если ключ неизвестен.

        Сравнение — `compare_digest` по байтам: заголовок приходит из сети и может
        нести не-ASCII, на котором строковая форма `compare_digest` падает.
        """
        presented = key.encode("utf-8")
        matched: str | None = None
        for name, known_key in self._keys_by_consumer.items():
            if secrets.compare_digest(known_key.encode("utf-8"), presented):
                matched = name
        return matched

    @property
    def consumers(self) -> tuple[str, ...]:
        return tuple(self._keys_by_consumer)
