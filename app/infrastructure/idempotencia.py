import hashlib
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencias import ContextoSolicitud
from app.core.errores import ErrorAplicacion


def hash_cuerpo(cuerpo: dict[str, Any]) -> str:
    serializado = json.dumps(cuerpo, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def buscar_respuesta(
    sesion: Session,
    contexto: ContextoSolicitud,
    operacion: str,
    clave: str,
    cuerpo: dict[str, Any],
) -> tuple[int, dict[str, Any]] | None:
    fila = (
        (
            sesion.execute(
                text("""
                SELECT hash_cuerpo, estado_http, respuesta
                FROM solicitud_idempotente
                WHERE identificador_organizacion=:org AND identificador_usuario=:usuario
                  AND operacion=:operacion AND clave=:clave AND fecha_hora_expiracion > now()
            """),
                {
                    "org": contexto.organizacion,
                    "usuario": contexto.usuario,
                    "operacion": operacion,
                    "clave": clave,
                },
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        return None
    if fila["hash_cuerpo"] != hash_cuerpo(cuerpo):
        raise ErrorAplicacion(
            "CONFLICTO_REVISION", "La clave de idempotencia fue utilizada con otro contenido.", 409
        )
    if fila["estado_http"] is None or fila["respuesta"] is None:
        raise ErrorAplicacion(
            "CONFLICTO_REVISION", "La operación con esta clave sigue en proceso.", 409
        )
    return int(fila["estado_http"]), dict(fila["respuesta"])


def reservar(
    sesion: Session,
    contexto: ContextoSolicitud,
    operacion: str,
    clave: str,
    cuerpo: dict[str, Any],
) -> bool:
    """Reserva la clave. Devuelve False si OTRA solicitud ya la tiene (vigente).

    ON CONFLICT espera a que la otra transacción termine: si confirmó, el llamador debe devolver
    su respuesta guardada; si falló, esta reserva sí se concreta. Una fila ya expirada se reutiliza.
    """
    resultado = sesion.execute(
        text("""
            INSERT INTO solicitud_idempotente
              (identificador_organizacion, identificador_usuario, operacion, clave, hash_cuerpo)
            VALUES (:org, :usuario, :operacion, :clave, :hash)
            ON CONFLICT (identificador_organizacion, identificador_usuario, operacion, clave)
            DO UPDATE SET hash_cuerpo = EXCLUDED.hash_cuerpo, estado_http = NULL, respuesta = NULL,
                          fecha_hora_creacion = now(),
                          fecha_hora_expiracion = now() + interval '24 hours'
            WHERE solicitud_idempotente.fecha_hora_expiracion <= now()
        """),
        {
            "org": contexto.organizacion,
            "usuario": contexto.usuario,
            "operacion": operacion,
            "clave": clave,
            "hash": hash_cuerpo(cuerpo),
        },
    )
    return bool(resultado.rowcount == 1)  # type: ignore[attr-defined]


def completar(
    sesion: Session,
    contexto: ContextoSolicitud,
    operacion: str,
    clave: str,
    estado_http: int,
    respuesta: dict[str, Any],
) -> None:
    sesion.execute(
        text("""
            UPDATE solicitud_idempotente SET estado_http=:estado, respuesta=CAST(:respuesta AS jsonb)
            WHERE identificador_organizacion=:org AND identificador_usuario=:usuario
              AND operacion=:operacion AND clave=:clave
        """),
        {
            "estado": estado_http,
            "respuesta": json.dumps(respuesta, default=str),
            "org": contexto.organizacion,
            "usuario": contexto.usuario,
            "operacion": operacion,
            "clave": clave,
        },
    )
