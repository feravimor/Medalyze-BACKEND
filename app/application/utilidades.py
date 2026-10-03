import base64
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.errores import ErrorAplicacion


def exigir_revision(if_match: str | None) -> int:
    if if_match is None:
        raise ErrorAplicacion("REVISION_REQUERIDA", "Debes indicar la revisión del recurso.", 428)
    valor = if_match.strip('"')
    if not valor.isdigit():
        raise ErrorAplicacion("ERROR_VALIDACION", "If-Match no contiene una revisión válida.", 422)
    return int(valor)


def codificar_cursor(fecha: datetime | date, identificador: UUID) -> str:
    raw = f"{fecha.isoformat()}|{identificador}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decodificar_cursor(cursor: str | None) -> tuple[str, UUID] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        fecha, identificador = base64.urlsafe_b64decode(padded).decode().split("|", 1)
        return fecha, UUID(identificador)
    except Exception as exc:
        raise ErrorAplicacion("ERROR_VALIDACION", "El cursor no es válido.", 422) from exc


def limpiar_json(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {k: limpiar_json(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [limpiar_json(v) for v in valor]
    if isinstance(valor, (UUID, Decimal)):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return valor
