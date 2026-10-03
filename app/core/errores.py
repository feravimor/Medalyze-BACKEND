from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ErrorAplicacion(Exception):
    codigo: str
    mensaje: str
    estado_http: int
    campos: list[dict[str, str]] = field(default_factory=list)
    bloqueos: list[dict[str, Any]] = field(default_factory=list)
    revision_actual: int | None = None


def no_encontrado(mensaje: str = "No se encontró el recurso solicitado.") -> ErrorAplicacion:
    return ErrorAplicacion("NO_ENCONTRADO", mensaje, 404)


def conflicto_revision(revision_actual: int) -> ErrorAplicacion:
    return ErrorAplicacion(
        "CONFLICTO_REVISION",
        "Estos datos cambiaron en otro dispositivo.",
        409,
        revision_actual=revision_actual,
    )
