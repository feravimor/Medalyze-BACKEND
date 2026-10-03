from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencias import ContextoSolicitud, obtener_contexto, obtener_sesion_protegida
from app.application.utilidades import limpiar_json

router = APIRouter()


@router.get("/inicio/resumen")
def resumen_inicio(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    conteos = (
        (
            sesion.execute(
                text("""
        SELECT count(*) total,
               count(*) FILTER (WHERE estado='CALCULADO') calculados,
               count(*) FILTER (WHERE estado IN ('BORRADOR','CAMBIOS_POR_REVISAR')) pendientes
        FROM tratamiento WHERE identificador_organizacion=:o AND estado<>'ARCHIVADO'
    """),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .one()
    )
    tiene_capacidad = bool(
        sesion.scalar(
            text(
                "SELECT 1 FROM perfil_capacidad_atencion WHERE identificador_organizacion=:o AND fecha_fin_vigencia IS NULL"
            ),
            {"o": contexto.organizacion},
        )
    )
    tiene_gastos = bool(
        sesion.scalar(
            text(
                "SELECT 1 FROM gasto_registrado WHERE identificador_organizacion=:o AND activo LIMIT 1"
            ),
            {"o": contexto.organizacion},
        )
    )
    bloqueo = sesion.scalar(
        text(
            "SELECT 1 FROM tratamiento WHERE identificador_organizacion=:o AND estado='CAMBIOS_POR_REVISAR' LIMIT 1"
        ),
        {"o": contexto.organizacion},
    )
    if conteos["total"] == 0:
        siguiente = {"codigo": "CREAR_TRATAMIENTO", "ruta": "/tratamientos"}
    elif not tiene_capacidad:
        siguiente = {"codigo": "REGISTRAR_TIEMPO", "ruta": "/datos/tiempo"}
    elif not tiene_gastos:
        siguiente = {"codigo": "REGISTRAR_COSTOS", "ruta": "/datos/costos"}
    elif bloqueo:
        siguiente = {"codigo": "REVISAR_CAMBIOS", "ruta": "/tratamientos"}
    elif conteos["pendientes"]:
        siguiente = {"codigo": "CALCULAR_TRATAMIENTO", "ruta": "/tratamientos"}
    else:
        siguiente = {"codigo": "TODO_LISTO", "ruta": "/tratamientos"}
    ultimo = (
        (
            sesion.execute(
                text("""
        SELECT h.identificador,h.identificador_tratamiento,h.fecha_hora_creacion fecha_creacion,h.costo_total,h.precio_sugerido,h.margen_porcentaje
        FROM hoja_costos_tratamiento h WHERE h.identificador_organizacion=:o ORDER BY h.fecha_hora_creacion DESC LIMIT 1
    """),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    recientes = (
        (
            sesion.execute(
                text("""
        SELECT h.identificador,h.identificador_tratamiento,t.nombre,h.fecha_hora_creacion fecha_creacion,h.costo_total,h.precio_sugerido,h.margen_porcentaje
        FROM hoja_costos_tratamiento h JOIN tratamiento t ON t.identificador=h.identificador_tratamiento
        WHERE h.identificador_organizacion=:o ORDER BY h.fecha_hora_creacion DESC LIMIT 5
    """),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .all()
    )
    return limpiar_json(
        {
            "siguiente_paso": siguiente,
            "kpi": {
                "con_calculo": conteos["calculados"],
                "pendientes": conteos["pendientes"],
                "total": conteos["total"],
            },
            "ultimo_resultado": dict(ultimo) if ultimo else None,
            "recientes": [dict(f) for f in recientes],
        }
    )
