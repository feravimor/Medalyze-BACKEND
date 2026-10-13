from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import fijar_contexto_organizacion, obtener_sesion
from app.core.errores import ErrorAplicacion
from app.core.seguridad import decodificar_token_acceso

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class ContextoSolicitud:
    usuario: UUID
    organizacion: UUID
    rol: str
    es_invitado: bool = False


def obtener_contexto(
    credencial: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> ContextoSolicitud:
    if credencial is None:
        raise ErrorAplicacion("SIN_AUTENTICACION", "Debes iniciar sesión.", 401)
    payload = decodificar_token_acceso(credencial.credentials)
    return ContextoSolicitud(
        usuario=UUID(payload["sub"]),
        organizacion=UUID(payload["org"]),
        rol=str(payload["rol"]),
        es_invitado=bool(payload.get("invitado", False)),
    )


def obtener_contexto_opcional(
    credencial: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> ContextoSolicitud | None:
    """Permite cerrar una sesión aunque el access token ya haya expirado."""
    if credencial is None:
        return None
    try:
        payload = decodificar_token_acceso(credencial.credentials)
    except ErrorAplicacion:
        return None
    return ContextoSolicitud(
        usuario=UUID(payload["sub"]),
        organizacion=UUID(payload["org"]),
        rol=str(payload["rol"]),
        es_invitado=bool(payload.get("invitado", False)),
    )


def obtener_sesion_protegida(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion),
) -> Iterator[Session]:
    sesion.begin()
    fijar_contexto_organizacion(sesion, contexto.organizacion)
    try:
        if contexto.es_invitado:
            vigente = sesion.scalar(
                text(
                    """
                SELECT 1
                FROM sesion_demo_invitado
                WHERE identificador_usuario=:usuario
                  AND identificador_organizacion=:organizacion
                  AND expira_en > now()
                    """
                ),
                {"usuario": contexto.usuario, "organizacion": contexto.organizacion},
            )
            if vigente is None:
                raise ErrorAplicacion("TOKEN_VENCIDO", "La sesión demo terminó.", 401)
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise


def exigir_propietario(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
) -> ContextoSolicitud:
    if contexto.rol != "PROPIETARIO":
        raise ErrorAplicacion("SIN_PERMISO", "No tienes permiso para realizar esta acción.", 403)
    return contexto


def exigir_cuenta_normal(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
) -> ContextoSolicitud:
    if contexto.es_invitado:
        raise ErrorAplicacion(
            "OPERACION_NO_DISPONIBLE_EN_DEMO",
            "Esta operación no está disponible en modo demo.",
            403,
        )
    return contexto
