import importlib
import importlib.util
from typing import cast

from transcription.domain.exceptions import EngineUnavailableError
from transcription.infrastructure.protocols.i_mlx_whisper_module import IMlxWhisperModule

MLX_WHISPER_PACKAGE = "mlx_whisper"


def load_mlx_whisper_module() -> IMlxWhisperModule:
    """Импортировать mlx_whisper по требованию.

    Импорт отложенный и не на уровне модуля: пакет ставится только на
    macOS/arm64, а модуль движка обязан оставаться импортируемым везде —
    иначе на Linux рассыпался бы весь composition root. Отсутствие пакета
    превращается в понятную доменную ошибку, а не в ModuleNotFoundError
    из середины запроса.
    """
    if importlib.util.find_spec(MLX_WHISPER_PACKAGE) is None:
        raise EngineUnavailableError(
            "Движок mlx недоступен: пакет mlx-whisper не установлен. "
            "Поставьте зависимости группы mlx (uv sync --extra mlx) на macOS/arm64 "
            "или переключите WHISPER_ENGINE на faster.",
        )
    return cast(IMlxWhisperModule, importlib.import_module(MLX_WHISPER_PACKAGE))
