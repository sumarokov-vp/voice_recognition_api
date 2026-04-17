from fastapi import Request

from api.composition.composition import Composition
from api.protocols.i_health_probe import IHealthProbe
from api.protocols.i_transcribe_use_case import ITranscribeUseCase


def get_composition(request: Request) -> Composition:
    composition: Composition = request.app.state.composition
    return composition


def get_transcribe_use_case(request: Request) -> ITranscribeUseCase:
    return get_composition(request).transcribe_use_case


def get_health_probe(request: Request) -> IHealthProbe:
    return get_composition(request).health_probe


def get_max_file_size_bytes(request: Request) -> int:
    return get_composition(request).config.max_file_size_bytes
