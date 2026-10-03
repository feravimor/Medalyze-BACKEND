import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import obtener_configuracion
from app.core.errores import ErrorAplicacion

configuracion = obtener_configuracion()
password_hasher = PasswordHasher()


def hash_contrasena(contrasena: str) -> str:
    return password_hasher.hash(contrasena)


def verificar_contrasena(hash_guardado: str, contrasena: str) -> bool:
    try:
        return password_hasher.verify(hash_guardado, contrasena)
    except VerifyMismatchError:
        return False


def crear_token_acceso(usuario: UUID, organizacion: UUID, rol: str) -> tuple[str, int]:
    segundos = configuracion.jwt_access_ttl_min * 60
    ahora = datetime.now(UTC)
    payload = {
        "sub": str(usuario),
        "org": str(organizacion),
        "rol": rol,
        "iat": ahora,
        "exp": ahora + timedelta(seconds=segundos),
        "tipo": "acceso",
    }
    return jwt.encode(payload, configuracion.jwt_secret, algorithm="HS256"), segundos


def decodificar_token_acceso(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, configuracion.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise ErrorAplicacion("TOKEN_VENCIDO", "El token de acceso venció.", 401) from exc
    except jwt.InvalidTokenError as exc:
        raise ErrorAplicacion("SIN_AUTENTICACION", "La sesión no es válida.", 401) from exc
    if payload.get("tipo") != "acceso":
        raise ErrorAplicacion("SIN_AUTENTICACION", "La sesión no es válida.", 401)
    return payload


def crear_token_actualizacion() -> str:
    return secrets.token_urlsafe(48)


def hash_token_actualizacion(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
