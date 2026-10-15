from fastapi import APIRouter, Depends, Header
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencias import (
    ContextoSolicitud,
    exigir_cuenta_normal,
    obtener_contexto,
    obtener_sesion_protegida,
)
from app.api.esquemas import (
    AceptacionAvisoPrivacidadEntrada,
    OnboardingActualizar,
    OrganizacionActualizar,
    PerfilActualizar,
)
from app.api.rutas.autenticacion import _estado_aviso_privacidad
from app.application.utilidades import exigir_revision, limpiar_json
from app.core import privacidad
from app.core.errores import ErrorAplicacion, conflicto_revision, no_encontrado
from app.infrastructure.idempotencia import buscar_respuesta, completar, reservar

router = APIRouter()


@router.post("/cuenta/aviso-privacidad/aceptacion")
def aceptar_aviso_privacidad(
    entrada: AceptacionAvisoPrivacidadEntrada,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    contexto: ContextoSolicitud = Depends(exigir_cuenta_normal),
    sesion: Session = Depends(obtener_sesion_protegida, scope="function"),
) -> dict:
    cuerpo = entrada.model_dump(mode="json")
    operacion = "aceptar-aviso-privacidad"
    repetida = buscar_respuesta(sesion, contexto, operacion, idempotency_key, cuerpo)
    if repetida:
        return repetida[1]
    if not reservar(sesion, contexto, operacion, idempotency_key, cuerpo):
        repetida = buscar_respuesta(sesion, contexto, operacion, idempotency_key, cuerpo)
        if repetida:
            return repetida[1]
        raise ErrorAplicacion(
            "CONFLICTO_REVISION",
            "La operación con esta clave sigue en proceso.",
            409,
        )
    if not entrada.acepta_aviso_privacidad:
        raise ErrorAplicacion(
            "AVISO_PRIVACIDAD_REQUERIDO",
            "Debes aceptar el Aviso de Privacidad vigente.",
            422,
        )
    if entrada.version_aviso_privacidad != privacidad.VERSION_AVISO_PRIVACIDAD_VIGENTE:
        raise ErrorAplicacion(
            "VERSION_AVISO_PRIVACIDAD_INVALIDA",
            "La versión del Aviso de Privacidad no está vigente.",
            422,
        )

    pertenece = sesion.execute(
        text(
            """
            SELECT 1 FROM membresia_usuario_en_organizacion
            WHERE identificador_usuario=:usuario
              AND identificador_organizacion=:organizacion
              AND activa
            """
        ),
        {"usuario": contexto.usuario, "organizacion": contexto.organizacion},
    ).scalar_one_or_none()
    if pertenece is None:
        raise ErrorAplicacion("SIN_AUTENTICACION", "La sesión no es válida.", 401)
    aceptado_en = sesion.scalar(
        text(
            """
            INSERT INTO aceptacion_aviso_privacidad (identificador_usuario, version_aviso)
            VALUES (:usuario,:version)
            ON CONFLICT (identificador_usuario, version_aviso) DO NOTHING
            RETURNING aceptado_en
            """
        ),
        {"usuario": contexto.usuario, "version": privacidad.VERSION_AVISO_PRIVACIDAD_VIGENTE},
    )
    estado = (
        {
            "version_aceptada": privacidad.VERSION_AVISO_PRIVACIDAD_VIGENTE,
            "aceptado_en": aceptado_en.isoformat(),
            "requiere_aceptar": False,
        }
        if aceptado_en is not None
        else _estado_aviso_privacidad(sesion, contexto.usuario, contexto.organizacion)
    )
    respuesta = {"aviso_privacidad": estado}
    completar(sesion, contexto, operacion, idempotency_key, 200, respuesta)
    return respuesta


def _perfil(sesion: Session, contexto: ContextoSolicitud) -> dict:
    fila = (
        (
            sesion.execute(
                text(
                    "SELECT identificador,nombre_completo nombre_para_mostrar,correo,revision FROM usuario_plataforma WHERE identificador=:u"
                ),
                {"u": contexto.usuario},
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        raise no_encontrado()
    especialidades: list[int] = list(
        (
            sesion.execute(
                text(
                    "SELECT identificador_especialidad FROM especialidad_seleccionada_por_usuario WHERE identificador_usuario=:u"
                ),
                {"u": contexto.usuario},
            )
        )
        .scalars()
        .all()
    )
    resultado = dict(fila)
    resultado["especialidades"] = especialidades
    return limpiar_json(resultado)


@router.get("/perfil")
def obtener_perfil(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida, scope="function"),
) -> dict:
    return _perfil(sesion, contexto)


@router.patch("/perfil")
def actualizar_perfil(
    entrada: PerfilActualizar,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(exigir_cuenta_normal),
    sesion: Session = Depends(obtener_sesion_protegida, scope="function"),
) -> dict:
    revision = exigir_revision(if_match)
    # Toda edición del perfil (nombre o especialidades) sube la revisión, para detectar ediciones simultáneas.
    actualizado = sesion.scalar(
        text(
            "UPDATE usuario_plataforma SET nombre_completo=coalesce(CAST(:nombre AS text),nombre_completo),revision=revision+1 WHERE identificador=:u AND revision=:revision RETURNING revision"
        ),
        {"nombre": entrada.nombre_para_mostrar, "u": contexto.usuario, "revision": revision},
    )
    if actualizado is None:
        actual = sesion.scalar(
            text("SELECT revision FROM usuario_plataforma WHERE identificador=:u"),
            {"u": contexto.usuario},
        )
        raise conflicto_revision(int(actual or 0))
    if entrada.especialidades is not None:
        sesion.execute(
            text(
                "DELETE FROM especialidad_seleccionada_por_usuario WHERE identificador_usuario=:u"
            ),
            {"u": contexto.usuario},
        )
        for especialidad in dict.fromkeys(
            entrada.especialidades
        ):  # sin repetidas, conservando el orden
            sesion.execute(
                text(
                    "INSERT INTO especialidad_seleccionada_por_usuario (identificador_usuario,identificador_especialidad) VALUES (:u,:e)"
                ),
                {"u": contexto.usuario, "e": especialidad},
            )
    return _perfil(sesion, contexto)


@router.get("/organizacion")
def obtener_organizacion(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida, scope="function"),
) -> dict:
    fila = (
        (
            sesion.execute(
                text(
                    "SELECT identificador,nombre_comercial,codigo_moneda,multiplo_redondeo,espaciado_por_defecto,revision FROM organizacion_consultorio WHERE identificador=:o"
                ),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        raise no_encontrado()
    return limpiar_json(dict(fila))


@router.patch("/organizacion")
def actualizar_organizacion(
    entrada: OrganizacionActualizar,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(exigir_cuenta_normal),
    sesion: Session = Depends(obtener_sesion_protegida, scope="function"),
) -> dict:
    revision = exigir_revision(if_match)
    actual = (
        (
            sesion.execute(
                text("SELECT * FROM organizacion_consultorio WHERE identificador=:o"),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if actual is None:
        raise no_encontrado()
    valores = entrada.model_dump(exclude_none=True)
    fila = (
        (
            sesion.execute(
                text("""
        UPDATE organizacion_consultorio SET
          nombre_comercial=:nombre,codigo_moneda=:moneda,multiplo_redondeo=:multiplo,
          espaciado_por_defecto=:espaciado,revision=revision+1
        WHERE identificador=:o AND revision=:revision
        RETURNING identificador,nombre_comercial,codigo_moneda,multiplo_redondeo,espaciado_por_defecto,revision
    """),
                {
                    "nombre": valores.get("nombre_comercial", actual["nombre_comercial"]),
                    "moneda": valores.get("codigo_moneda", actual["codigo_moneda"]),
                    "multiplo": valores.get("multiplo_redondeo", actual["multiplo_redondeo"]),
                    "espaciado": valores.get(
                        "espaciado_por_defecto", actual["espaciado_por_defecto"]
                    ),
                    "o": contexto.organizacion,
                    "revision": revision,
                },
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        raise conflicto_revision(int(actual["revision"]))
    if "multiplo_redondeo" in valores or "espaciado_por_defecto" in valores:
        sesion.execute(
            text(
                "UPDATE tratamiento SET estado='CAMBIOS_POR_REVISAR' WHERE identificador_organizacion=:o AND estado='CALCULADO'"
            ),
            {"o": contexto.organizacion},
        )
    return limpiar_json(dict(fila))


@router.get("/especialidades")
def listar_especialidades(sesion: Session = Depends(obtener_sesion_protegida, scope="function")) -> dict:
    filas = (
        (
            sesion.execute(
                text(
                    "SELECT identificador,clave,nombre FROM especialidad_odontologica ORDER BY orden"
                )
            )
        )
        .mappings()
        .all()
    )
    return {"elementos": [limpiar_json(dict(f)) for f in filas]}


def _onboarding(sesion: Session, contexto: ContextoSolicitud) -> dict:
    fila = (
        (
            sesion.execute(
                text(
                    "SELECT ruta::text,situacion::text,ultimo_paso,seleccion_parcial,completado,revision FROM preferencias_onboarding_usuario WHERE identificador_usuario=:u AND identificador_organizacion=:o"
                ),
                {"u": contexto.usuario, "o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        raise no_encontrado()
    return limpiar_json(dict(fila))


@router.get("/onboarding")
def obtener_onboarding(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida, scope="function"),
) -> dict:
    return _onboarding(sesion, contexto)


@router.patch("/onboarding")
def actualizar_onboarding(
    entrada: OnboardingActualizar,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(exigir_cuenta_normal),
    sesion: Session = Depends(obtener_sesion_protegida, scope="function"),
) -> dict:
    revision = exigir_revision(if_match)
    actual = (
        (
            sesion.execute(
                text(
                    "SELECT * FROM preferencias_onboarding_usuario WHERE identificador_usuario=:u AND identificador_organizacion=:o"
                ),
                {"u": contexto.usuario, "o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if actual is None:
        raise no_encontrado()
    valores = entrada.model_dump(exclude_none=True)
    fila = sesion.scalar(
        text("""
        UPDATE preferencias_onboarding_usuario SET ruta=:ruta,situacion=:situacion,ultimo_paso=:paso,
          seleccion_parcial=CAST(:seleccion AS jsonb),completado=:completado,revision=revision+1
        WHERE identificador=:id AND revision=:revision RETURNING revision
    """),
        {
            "ruta": valores.get("ruta", actual["ruta"]),
            "situacion": valores.get("situacion", actual["situacion"]),
            "paso": valores.get("ultimo_paso", actual["ultimo_paso"]),
            "seleccion": __import__("json").dumps(
                valores.get("seleccion_parcial", actual["seleccion_parcial"])
            ),
            "completado": valores.get("completado", actual["completado"]),
            "id": actual["identificador"],
            "revision": revision,
        },
    )
    if fila is None:
        raise conflicto_revision(int(actual["revision"]))
    return _onboarding(sesion, contexto)
