from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from psycopg import errors as errores_pg
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencias import ContextoSolicitud, obtener_contexto, obtener_sesion_protegida
from app.api.esquemas import InsumoEntrada
from app.application.utilidades import exigir_revision, limpiar_json
from app.core.errores import ErrorAplicacion, conflicto_revision, no_encontrado

router = APIRouter()


@router.get("/unidades-medida")
def unidades(sesion: Session = Depends(obtener_sesion_protegida)) -> dict:
    filas = (
        (
            sesion.execute(
                text("SELECT codigo,nombre FROM unidad_medida_insumo ORDER BY orden")
            )
        )
        .mappings()
        .all()
    )
    return {"elementos": [dict(f) for f in filas]}


def _obtener_insumo(
    sesion: Session, contexto: ContextoSolicitud, identificador: UUID
) -> dict:
    fila = (
        (
            sesion.execute(
                text("""
        SELECT i.identificador,i.nombre,i.presentacion,i.codigo_unidad,i.cantidad_contenida,
               p.precio_presentacion,p.costo_unitario,(i.fecha_hora_archivado IS NOT NULL) archivado,
               (SELECT count(*) FROM linea_receta_insumos_tratamiento l JOIN version_configuracion_tratamiento v ON v.identificador=l.identificador_version_configuracion JOIN tratamiento t ON t.identificador=v.identificador_tratamiento WHERE l.identificador_insumo=i.identificador AND t.identificador_organizacion=:o) usado_en_recetas,
               i.revision
        FROM insumo_clinico i LEFT JOIN LATERAL (SELECT precio_presentacion,costo_unitario FROM precio_historico_insumo WHERE identificador_insumo=i.identificador ORDER BY fecha_inicio_vigencia DESC,fecha_hora_creacion DESC LIMIT 1) p ON true
        WHERE i.identificador=:id AND i.identificador_organizacion=:o
    """),
                {"id": identificador, "o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        raise no_encontrado()
    return limpiar_json(dict(fila))


@router.get("/insumos")
def listar_insumos(
    busqueda: str = "",
    archivados: bool = False,
    limite: int = Query(default=20, ge=1, le=100),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    filas = (
        (
            sesion.execute(
                text("""
        SELECT i.identificador,i.nombre,i.presentacion,i.codigo_unidad,i.cantidad_contenida,
               p.precio_presentacion,p.costo_unitario,(i.fecha_hora_archivado IS NOT NULL) archivado,
               (SELECT count(*) FROM linea_receta_insumos_tratamiento l WHERE l.identificador_insumo=i.identificador) usado_en_recetas,
               i.revision
        FROM insumo_clinico i LEFT JOIN LATERAL (SELECT precio_presentacion,costo_unitario FROM precio_historico_insumo WHERE identificador_insumo=i.identificador ORDER BY fecha_inicio_vigencia DESC,fecha_hora_creacion DESC LIMIT 1) p ON true
        WHERE i.identificador_organizacion=:o AND (:archivados OR i.fecha_hora_archivado IS NULL)
          AND (:busqueda='' OR i.nombre ILIKE '%' || :busqueda || '%')
        ORDER BY i.nombre LIMIT :limite
    """),
                {
                    "o": contexto.organizacion,
                    "archivados": archivados,
                    "busqueda": busqueda,
                    "limite": limite,
                },
            )
        )
        .mappings()
        .all()
    )
    return {"elementos": [limpiar_json(dict(f)) for f in filas], "siguiente_cursor": None}


@router.post("/insumos", status_code=status.HTTP_201_CREATED)
def crear_insumo(
    entrada: InsumoEntrada,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    try:
        identificador = sesion.scalar(
            text("""
            INSERT INTO insumo_clinico (identificador_organizacion,nombre,presentacion,codigo_unidad,cantidad_contenida)
            VALUES (:o,:nombre,:presentacion,:unidad,:cantidad) RETURNING identificador
        """),
            {
                "o": contexto.organizacion,
                "nombre": entrada.nombre,
                "presentacion": entrada.presentacion,
                "unidad": entrada.codigo_unidad,
                "cantidad": entrada.cantidad_contenida,
            },
        )
    except IntegrityError as exc:
        if isinstance(exc.orig, errores_pg.UniqueViolation):
            raise ErrorAplicacion(
                "INSUMO_DUPLICADO", "Ya tienes un insumo con ese nombre.", 409
            ) from exc
        raise  # unidad inexistente, cantidad inválida…: el manejador global responde 422
    sesion.execute(
        text(
            "INSERT INTO precio_historico_insumo (identificador_insumo,precio_presentacion,cantidad_contenida) VALUES (:id,:precio,:cantidad)"
        ),
        {
            "id": identificador,
            "precio": entrada.precio_presentacion,
            "cantidad": entrada.cantidad_contenida,
        },
    )
    return _obtener_insumo(sesion, contexto, identificador)


@router.patch("/insumos/{identificador}")
def actualizar_insumo(
    identificador: UUID,
    entrada: InsumoEntrada,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    revision = exigir_revision(if_match)
    anterior = (
        (
            sesion.execute(
                text(
                    """SELECT i.revision,i.cantidad_contenida,p.precio_presentacion FROM insumo_clinico i LEFT JOIN LATERAL (SELECT precio_presentacion FROM precio_historico_insumo WHERE identificador_insumo=i.identificador ORDER BY fecha_inicio_vigencia DESC,fecha_hora_creacion DESC LIMIT 1) p ON true WHERE i.identificador=:id AND i.identificador_organizacion=:o"""
                ),
                {"id": identificador, "o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if anterior is None:
        raise no_encontrado()
    try:
        actualizado = sesion.scalar(
            text(
                """UPDATE insumo_clinico SET nombre=:nombre,presentacion=:presentacion,codigo_unidad=:unidad,cantidad_contenida=:cantidad,revision=revision+1 WHERE identificador=:id AND identificador_organizacion=:o AND revision=:revision RETURNING identificador"""
            ),
            {
                "nombre": entrada.nombre,
                "presentacion": entrada.presentacion,
                "unidad": entrada.codigo_unidad,
                "cantidad": entrada.cantidad_contenida,
                "id": identificador,
                "o": contexto.organizacion,
                "revision": revision,
            },
        )
    except IntegrityError as exc:
        if isinstance(exc.orig, errores_pg.UniqueViolation):
            raise ErrorAplicacion(
                "INSUMO_DUPLICADO", "Ya tienes un insumo con ese nombre.", 409
            ) from exc
        raise
    if actualizado is None:
        raise conflicto_revision(int(anterior["revision"]))
    if (
        anterior["precio_presentacion"] != entrada.precio_presentacion
        or anterior["cantidad_contenida"] != entrada.cantidad_contenida
    ):
        sesion.execute(
            text(
                "INSERT INTO precio_historico_insumo (identificador_insumo,precio_presentacion,cantidad_contenida) VALUES (:id,:precio,:cantidad)"
            ),
            {
                "id": identificador,
                "precio": entrada.precio_presentacion,
                "cantidad": entrada.cantidad_contenida,
            },
        )
        sesion.execute(
            text(
                """UPDATE tratamiento t SET estado='CAMBIOS_POR_REVISAR' WHERE t.estado='CALCULADO' AND EXISTS (SELECT 1 FROM version_configuracion_tratamiento v JOIN linea_receta_insumos_tratamiento l ON l.identificador_version_configuracion=v.identificador WHERE v.identificador_tratamiento=t.identificador AND l.identificador_insumo=:id)"""
            ),
            {"id": identificador},
        )
    return _obtener_insumo(sesion, contexto, identificador)


@router.delete("/insumos/{identificador}", status_code=204)
def eliminar_insumo(
    identificador: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> Response:
    revision = exigir_revision(if_match)
    usos = sesion.scalar(
        text(
            "SELECT count(*) FROM linea_receta_insumos_tratamiento WHERE identificador_insumo=:id"
        ),
        {"id": identificador},
    )
    if usos:
        raise ErrorAplicacion(
            "INSUMO_EN_USO",
            f"Este insumo se usa en {usos} receta(s); archívalo en lugar de eliminarlo.",
            409,
        )
    eliminado = sesion.scalar(
        text(
            "DELETE FROM insumo_clinico WHERE identificador=:id AND identificador_organizacion=:o AND revision=:revision RETURNING identificador"
        ),
        {"id": identificador, "o": contexto.organizacion, "revision": revision},
    )
    if eliminado is None:
        actual = sesion.scalar(
            text(
                "SELECT revision FROM insumo_clinico WHERE identificador=:id AND identificador_organizacion=:o"
            ),
            {"id": identificador, "o": contexto.organizacion},
        )
        if actual is None:
            raise no_encontrado()
        raise conflicto_revision(int(actual))
    return Response(status_code=204)


def _cambiar_archivo(
    identificador: UUID,
    archivar: bool,
    revision: int,
    contexto: ContextoSolicitud,
    sesion: Session,
) -> dict:
    valor = "now()" if archivar else "NULL"
    fila = sesion.scalar(
        text(
            f"UPDATE insumo_clinico SET fecha_hora_archivado={valor},revision=revision+1 WHERE identificador=:id AND identificador_organizacion=:o AND revision=:revision RETURNING identificador"
        ),
        {"id": identificador, "o": contexto.organizacion, "revision": revision},
    )
    if fila is None:
        actual = sesion.scalar(
            text(
                "SELECT revision FROM insumo_clinico WHERE identificador=:id AND identificador_organizacion=:o"
            ),
            {"id": identificador, "o": contexto.organizacion},
        )
        if actual is None:
            raise no_encontrado()
        raise conflicto_revision(int(actual))
    sesion.execute(
        text(
            """UPDATE tratamiento t SET estado='CAMBIOS_POR_REVISAR' WHERE t.estado='CALCULADO' AND EXISTS (SELECT 1 FROM version_configuracion_tratamiento v JOIN linea_receta_insumos_tratamiento l ON l.identificador_version_configuracion=v.identificador WHERE v.identificador_tratamiento=t.identificador AND l.identificador_insumo=:id)"""
        ),
        {"id": identificador},
    )
    return _obtener_insumo(sesion, contexto, identificador)


@router.post("/insumos/{identificador}/archivar")
def archivar_insumo(
    identificador: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    return _cambiar_archivo(identificador, True, exigir_revision(if_match), contexto, sesion)


@router.post("/insumos/{identificador}/restaurar")
def restaurar_insumo(
    identificador: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    return _cambiar_archivo(identificador, False, exigir_revision(if_match), contexto, sesion)


@router.get("/insumos/{identificador}/precios")
def precios_insumo(
    identificador: UUID,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    existe = sesion.scalar(
        text(
            "SELECT 1 FROM insumo_clinico WHERE identificador=:id AND identificador_organizacion=:o"
        ),
        {"id": identificador, "o": contexto.organizacion},
    )
    if not existe:
        raise no_encontrado()
    filas = (
        (
            sesion.execute(
                text(
                    "SELECT identificador,precio_presentacion,cantidad_contenida,costo_unitario,fecha_inicio_vigencia FROM precio_historico_insumo WHERE identificador_insumo=:id ORDER BY fecha_inicio_vigencia DESC,fecha_hora_creacion DESC"
                ),
                {"id": identificador},
            )
        )
        .mappings()
        .all()
    )
    return {"elementos": [limpiar_json(dict(f)) for f in filas]}
