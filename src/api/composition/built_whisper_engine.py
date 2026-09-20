from dataclasses import dataclass

from transcription.application.protocols.i_whisper_engine import IWhisperEngine


@dataclass(frozen=True)
class BuiltWhisperEngine:
    """Собранный движок вместе с тем, как он представляется наружу.

    model и device нужны health-пробе: у разных движков это разные вещи
    (размер модели и cuda против HF repo id и metal), а формат ответа
    /health остаётся прежним.
    """

    engine: IWhisperEngine
    model: str
    device: str
    language: str
