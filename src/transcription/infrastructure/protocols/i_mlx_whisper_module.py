from typing import Any, Protocol


class IMlxWhisperModule(Protocol):
    """Контракт пакета mlx_whisper в том объёме, в котором его использует движок.

    Protocol объявлен на стороне потребителя: движок описывает ровно ту одну
    функцию, которая ему нужна, и не зависит от типов самого пакета — его
    может не быть в окружении (Linux).
    """

    def transcribe(
        self,
        audio: str,
        *,
        path_or_hf_repo: str,
        language: str | None,
        initial_prompt: str | None,
    ) -> dict[str, Any]: ...
