from fastapi import APIRouter, Depends, Header
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencias import ContextoSolicitud, obtener_contexto, obtener_sesion_protegida
from app.api.esquemas import OnboardingActualizar, OrganizacionActualizar, PerfilActualizar
from app.application.utilidades import exigir_revision, limpiar_json
from app.core.errores import conflicto_revision, no_encontrado

router = APIRouter()


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
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    return _perfil(sesion, contexto)


@router.patch("/perfil")
def actualizar_perfil(
    entrada: PerfilActualizar,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    revision = exigir_revision(if_match)
    if entrada.nombre_para_mostrar is not None:
        actualizado = sesion.scalar(
            text(
                "UPDATE usuario_plataforma SET nombre_completo=:nombre,revision=revision+1 WHERE identificador=:u AND revision=:revision RETURNING revision"
            ),
            {"nombre": entrada.nombre_para_mostrar, "u": contexto.usuario, "revision": revision},
        )
    else:
        actual = sesion.scalar(
            text("SELECT revision FROM usuario_plataforma WHERE identificador=:u"),
            {"u": contexto.usuario},
        )
        actualizado = actual if actual == revision else None
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
        for especialidad in entrada.especialidades:
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
    sesion: Session = Depends(obtener_sesion_protegida),
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
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
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
def listar_especialidades(sesion: Session = Depends(obtener_sesion_protegida)) -> dict:
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
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    return _onboarding(sesion, contexto)


@router.patch("/onboarding")
def actualizar_onboarding(
    entrada: OnboardingActualizar,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
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
