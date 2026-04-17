import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class UploadTempFile:
    """Контекстный помощник: сохранить загруженные байты во временный файл."""

    def __init__(self, suffix: str) -> None:
        self._suffix = suffix

    @contextmanager
    def write(self, payload: bytes) -> Iterator[Path]:
        with tempfile.NamedTemporaryFile(suffix=self._suffix, delete=True) as handle:
            handle.write(payload)
            handle.flush()
            yield Path(handle.name)
