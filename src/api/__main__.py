import sys

import uvicorn

from api.app_factory import create_app
from api.composition.api_config import ApiConfig
from transcription.domain.exceptions import TranscriptionError


def main() -> int:
    config = ApiConfig()
    try:
        app = create_app(config)
    except TranscriptionError as exc:
        sys.stderr.write(f"Не удалось инициализировать приложение: {exc}\n")
        return 1

    uvicorn.run(app, host=config.api_host, port=config.api_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
