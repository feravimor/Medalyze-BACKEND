from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencias import (
    ContextoSolicitud,
    obtener_contexto,
    obtener_contexto_opcional,
    obtener_sesion_protegida,
)
from app.api.esquemas import InicioSesionEntrada, RegistroEntrada, RenovacionEntrada
from app.core.config import obtener_configuracion
from app.core.database import fijar_contexto_organizacion, obtener_sesion
from app.core.errores import ErrorAplicacion
from app.core.rate_limit import limitar_intentos
from app.core.seguridad import (
    crear_token_acceso,
    crear_token_actualizacion,
    hash_contrasena,
    hash_token_actualizacion,
    verificar_contrasena,
)

router = APIRouter()
configuracion = obtener_configuracion()


def _crear_sesion(
    sesion: Session,
    usuario: UUID,
    organizacion: UUID,
    rol: str,
) -> tuple[str, str, int]:
    acceso, segundos = crear_token_acceso(usuario, organizacion, rol)
    actualizacion = crear_token_actualizacion()
    sesion.execute(
        text("""
            INSERT INTO token_actualizacion_sesion
              (identificador_usuario, identificador_organizacion, hash_token, fecha_hora_expiracion)
            VALUES (:usuario, :organizacion, :hash, :expira)
        """),
        {
            "usuario": usuario,
            "organizacion": organizacion,
            "hash": hash_token_actualizacion(actualizacion),
            "expira": datetime.now(UTC) + timedelta(days=configuracion.refresh_ttl_days),
        },
    )
    return acceso, actualizacion, segundos


def _respuesta_sesion(fila: dict, acceso: str, segundos: int) -> dict:
    respuesta = {
        "token_acceso": acceso,
        "expira_en_segundos": segundos,
        "usuario": {
            "identificador": fila["usuario_id"],
            "nombre_completo": fila["nombre_completo"],
            "correo": fila["correo"],
            "rol": fila["rol"],
        },
        "organizacion": {
            "identificador": fila["organizacion_id"],
            "nombre_comercial": fila["nombre_comercial"],
            "codigo_moneda": fila["codigo_moneda"],
            "multiplo_redondeo": str(fila["multiplo_redondeo"]),
            "espaciado_por_defecto": fila["espaciado_por_defecto"],
            "revision": fila["organizacion_revision"],
        },
        "onboarding_completado": fila["onboarding_completado"],
    }
    return respuesta


def _establecer_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=configuracion.refresh_cookie_name,
        value=token,
        max_age=configuracion.refresh_ttl_days * 24 * 60 * 60,
        expires=configuracion.refresh_ttl_days * 24 * 60 * 60,
        path=configuracion.refresh_cookie_path,
        secure=configuracion.refresh_cookie_secure,
        httponly=True,
        samesite=configuracion.refresh_cookie_samesite,
    )


def _expirar_cookie(response: Response) -> None:
    response.delete_cookie(
        key=configuracion.refresh_cookie_name,
        path=configuracion.refresh_cookie_path,
        secure=configuracion.refresh_cookie_secure,
        httponly=True,
        samesite=configuracion.refresh_cookie_samesite,
    )


@router.post("/registro", status_code=status.HTTP_201_CREATED)
def registro(
    entrada: RegistroEntrada,
    request: Request,
    response: Response,
    sesion: Session = Depends(obtener_sesion),
) -> dict:
    limitar_intentos(f"registro:{request.client.host if request.client else 'desconocido'}")
    with sesion.begin():
        existe = sesion.scalar(
            text("SELECT 1 FROM usuario_plataforma WHERE correo=:correo"),
            {"correo": str(entrada.correo).lower()},
        )
        if existe:
            raise ErrorAplicacion(
                "CORREO_YA_REGISTRADO", "Ya existe una cuenta con este correo.", 409
            )
        usuario = sesion.scalar(
            text(
                "INSERT INTO usuario_plataforma (correo, hash_contrasena, nombre_completo) VALUES (:correo,:hash,:nombre) RETURNING identificador"
            ),
            {
                "correo": str(entrada.correo).lower(),
                "hash": hash_contrasena(entrada.contrasena),
                "nombre": entrada.nombre_completo,
            },
        )
        organizacion = sesion.scalar(
            text(
                "INSERT INTO organizacion_consultorio (nombre_comercial) VALUES (:nombre) RETURNING identificador"
            ),
            {"nombre": entrada.nombre_consultorio or f"Consultorio de {entrada.nombre_completo}"},
        )
        fijar_contexto_organizacion(sesion, organizacion)
        sesion.execute(
            text(
                "INSERT INTO membresia_usuario_en_organizacion (identificador_usuario, identificador_organizacion, rol) VALUES (:u,:o,'PROPIETARIO')"
            ),
            {"u": usuario, "o": organizacion},
        )
        sesion.execute(
            text(
                "INSERT INTO preferencias_onboarding_usuario (identificador_usuario, identificador_organizacion) VALUES (:u,:o)"
            ),
            {"u": usuario, "o": organizacion},
        )
        acceso, actualizacion, segundos = _crear_sesion(
            sesion, usuario, organizacion, "PROPIETARIO"
        )
        fila = {
            "usuario_id": usuario,
            "nombre_completo": entrada.nombre_completo,
            "correo": str(entrada.correo).lower(),
            "rol": "PROPIETARIO",
            "organizacion_id": organizacion,
            "nombre_comercial": entrada.nombre_consultorio
            or f"Consultorio de {entrada.nombre_completo}",
            "codigo_moneda": "MXN",
            "multiplo_redondeo": 50,
            "espaciado_por_defecto": None,
            "organizacion_revision": 0,
            "onboarding_completado": False,
        }
    _establecer_cookie(response, actualizacion)
    return _respuesta_sesion(fila, acceso, segundos)


@router.post("/inicio-sesion")
def inicio_sesion(
    entrada: InicioSesionEntrada,
    request: Request,
    response: Response,
    sesion: Session = Depends(obtener_sesion),
) -> dict:
    limitar_intentos(f"inicio-sesion:{request.client.host if request.client else 'desconocido'}")
    with sesion.begin():
        fila = (
            (
                sesion.execute(
                    text("""
            SELECT u.identificador usuario_id, u.nombre_completo, u.correo, u.hash_contrasena,
                   m.rol::text rol, o.identificador organizacion_id, o.nombre_comercial, o.codigo_moneda,
                   o.multiplo_redondeo, o.espaciado_por_defecto, o.revision organizacion_revision,
                   coalesce(p.completado,false) onboarding_completado
            FROM usuario_plataforma u JOIN membresia_usuario_en_organizacion m ON m.identificador_usuario=u.identificador AND m.activa
            JOIN organizacion_consultorio o ON o.identificador=m.identificador_organizacion
            LEFT JOIN preferencias_onboarding_usuario p ON p.identificador_usuario=u.identificador
            WHERE u.correo=:correo LIMIT 1
        """),
                    {"correo": str(entrada.correo).lower()},
                )
            )
            .mappings()
            .first()
        )
        if fila is None or not verificar_contrasena(fila["hash_contrasena"], entrada.contrasena):
            raise ErrorAplicacion("CREDENCIALES_INVALIDAS", "Correo o contraseña incorrectos.", 401)
        fijar_contexto_organizacion(sesion, fila["organizacion_id"])
        onboarding_completado = sesion.scalar(
            text(
                "SELECT completado FROM preferencias_onboarding_usuario WHERE identificador_usuario=:u"
            ),
            {"u": fila["usuario_id"]},
        )
        sesion.execute(
            text(
                "UPDATE usuario_plataforma SET fecha_hora_ultimo_inicio_sesion=now() WHERE identificador=:id"
            ),
            {"id": fila["usuario_id"]},
        )
        acceso, actualizacion, segundos = _crear_sesion(
            sesion, fila["usuario_id"], fila["organizacion_id"], fila["rol"]
        )
        datos_sesion = dict(fila)
        datos_sesion["onboarding_completado"] = bool(onboarding_completado)
    _establecer_cookie(response, actualizacion)
    return _respuesta_sesion(datos_sesion, acceso, segundos)


@router.post("/renovacion")
def renovacion(
    response: Response,
    request: Request,
    entrada: RenovacionEntrada | None = None,
    refresh_cookie: str | None = Cookie(default=None, alias=configuracion.refresh_cookie_name),
    sesion: Session = Depends(obtener_sesion),
) -> dict:
    limitar_intentos(f"renovacion:{request.client.host if request.client else 'desconocido'}")
    token_actualizacion = (entrada.token_actualizacion if entrada else None) or refresh_cookie
    if not token_actualizacion:
        raise ErrorAplicacion("SIN_AUTENTICACION", "La sesión no es válida.", 401)
    token_hash = hash_token_actualizacion(token_actualizacion)
    reutilizado = False
    respuesta: dict | None = None
    with sesion.begin():
        token = (
            (
                sesion.execute(
                    text(
                        "SELECT * FROM token_actualizacion_sesion WHERE hash_token=:hash FOR UPDATE"
                    ),
                    {"hash": token_hash},
                )
            )
            .mappings()
            .first()
        )
        if token is None or token["fecha_hora_expiracion"] <= datetime.now(UTC):
            raise ErrorAplicacion("TOKEN_VENCIDO", "La sesión terminó.", 401)
        if token["fecha_hora_revocacion"] is not None:
            # Reutilización de un token ya rotado: se revoca TODA la familia del usuario.
            # El error se lanza DESPUÉS de salir de este bloque. Si se lanzara aquí dentro, el
            # rollback desharía esta revocación y la defensa no tendría ningún efecto.
            sesion.execute(
                text(
                    "UPDATE token_actualizacion_sesion SET fecha_hora_revocacion=coalesce(fecha_hora_revocacion,now()) WHERE identificador_usuario=:u"
                ),
                {"u": token["identificador_usuario"]},
            )
            reutilizado = True
        else:
            fijar_contexto_organizacion(sesion, token["identificador_organizacion"])
            fila = (
                (
                    sesion.execute(
                        text("""
            SELECT u.identificador usuario_id,u.nombre_completo,u.correo,m.rol::text rol,
                   o.identificador organizacion_id,o.nombre_comercial,o.codigo_moneda,o.multiplo_redondeo,
                   o.espaciado_por_defecto,o.revision organizacion_revision,coalesce(p.completado,false) onboarding_completado
            FROM usuario_plataforma u JOIN membresia_usuario_en_organizacion m ON m.identificador_usuario=u.identificador
            JOIN organizacion_consultorio o ON o.identificador=m.identificador_organizacion
            LEFT JOIN preferencias_onboarding_usuario p ON p.identificador_usuario=u.identificador
            WHERE u.identificador=:u AND o.identificador=:o AND m.activa
        """),
                        {
                            "u": token["identificador_usuario"],
                            "o": token["identificador_organizacion"],
                        },
                    )
                )
                .mappings()
                .one()
            )
            nuevo_acceso, nuevo_refresh, segundos = _crear_sesion(
                sesion, fila["usuario_id"], fila["organizacion_id"], fila["rol"]
            )
            nuevo_id = sesion.scalar(
                text("SELECT identificador FROM token_actualizacion_sesion WHERE hash_token=:hash"),
                {"hash": hash_token_actualizacion(nuevo_refresh)},
            )
            sesion.execute(
                text(
                    "UPDATE token_actualizacion_sesion SET fecha_hora_revocacion=now(), reemplazado_por=:nuevo WHERE identificador=:id"
                ),
                {"nuevo": nuevo_id, "id": token["identificador"]},
            )
            respuesta = _respuesta_sesion(dict(fila), nuevo_acceso, segundos)
            _establecer_cookie(response, nuevo_refresh)
    if reutilizado:
        raise ErrorAplicacion(
            "SIN_AUTENTICACION", "Se detectó reutilización de una sesión revocada.", 401
        )
    assert respuesta is not None
    return respuesta


@router.post("/cierre-sesion", status_code=status.HTTP_204_NO_CONTENT)
def cierre_sesion(
    response: Response,
    entrada: RenovacionEntrada | None = None,
    refresh_cookie: str | None = Cookie(default=None, alias=configuracion.refresh_cookie_name),
    contexto: ContextoSolicitud | None = Depends(obtener_contexto_opcional),
    sesion: Session = Depends(obtener_sesion),
) -> Response:
    token = (entrada.token_actualizacion if entrada else None) or refresh_cookie
    if token is None and contexto is None:
        raise ErrorAplicacion("SIN_AUTENTICACION", "Debes iniciar sesión.", 401)
    with sesion.begin():
        if token and contexto is not None:
            sesion.execute(
                text(
                    "UPDATE token_actualizacion_sesion SET fecha_hora_revocacion=coalesce(fecha_hora_revocacion,now()) WHERE identificador_usuario=:u AND hash_token=:hash"
                ),
                {"u": contexto.usuario, "hash": hash_token_actualizacion(token)},
            )
        elif token:
            sesion.execute(
                text(
                    "UPDATE token_actualizacion_sesion SET fecha_hora_revocacion=coalesce(fecha_hora_revocacion,now()) WHERE hash_token=:hash"
                ),
                {"hash": hash_token_actualizacion(token)},
            )
        elif contexto is not None:
            sesion.execute(
                text(
                    "UPDATE token_actualizacion_sesion SET fecha_hora_revocacion=now() WHERE identificador_usuario=:u AND fecha_hora_revocacion IS NULL"
                ),
                {"u": contexto.usuario},
            )
    _expirar_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/usuario-actual")
def usuario_actual(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    fila = (
        (
            sesion.execute(
                text("""
        SELECT u.identificador usuario_id,u.nombre_completo,u.correo,m.rol::text rol,
               o.identificador organizacion_id,o.nombre_comercial,o.codigo_moneda,o.multiplo_redondeo,
               o.espaciado_por_defecto,o.revision organizacion_revision,coalesce(p.completado,false) onboarding_completado
        FROM usuario_plataforma u JOIN membresia_usuario_en_organizacion m ON m.identificador_usuario=u.identificador
        JOIN organizacion_consultorio o ON o.identificador=m.identificador_organizacion
        LEFT JOIN preferencias_onboarding_usuario p ON p.identificador_usuario=u.identificador
        WHERE u.identificador=:u AND o.identificador=:o AND m.activa
    """),
                {"u": contexto.usuario, "o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        raise ErrorAplicacion("SIN_AUTENTICACION", "La sesión no es válida.", 401)
    acceso, segundos = crear_token_acceso(contexto.usuario, contexto.organizacion, contexto.rol)
    return _respuesta_sesion(dict(fila), acceso, segundos)
