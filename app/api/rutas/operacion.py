from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencias import ContextoSolicitud, obtener_contexto, obtener_sesion_protegida
from app.api.esquemas import EquipoEntrada, GastoEntrada, PerfilCapacidadEntrada
from app.application.utilidades import exigir_revision, limpiar_json
from app.core.errores import conflicto_revision, no_encontrado
from app.domain.costeo.periodicidad import equivalente_mensual
from app.infrastructure.repositorios_costeo import (
    RepositorioEquiposSQLAlchemy,
    RepositorioGastosSQLAlchemy,
)

router = APIRouter()


@router.get("/perfil-capacidad")
def obtener_capacidad(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    fila = (
        (
            sesion.execute(
                text(
                    "SELECT identificador,dias_por_semana,horas_por_dia,porcentaje_ocupacion,ocupacion_confirmada,fecha_inicio_vigencia,revision FROM perfil_capacidad_atencion WHERE identificador_organizacion=:o AND fecha_fin_vigencia IS NULL"
                ),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        raise no_encontrado("Aún no existe un perfil de capacidad.")
    return limpiar_json(dict(fila))


@router.put("/perfil-capacidad")
def guardar_capacidad(
    entrada: PerfilCapacidadEntrada,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    revision = exigir_revision(if_match)
    actual = (
        (
            sesion.execute(
                text(
                    "SELECT identificador,revision FROM perfil_capacidad_atencion WHERE identificador_organizacion=:o AND fecha_fin_vigencia IS NULL FOR UPDATE"
                ),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if actual is None and revision != 0:
        raise conflicto_revision(0)
    if actual is not None:
        if actual["revision"] != revision:
            raise conflicto_revision(int(actual["revision"]))
        sesion.execute(
            text(
                "UPDATE perfil_capacidad_atencion SET fecha_fin_vigencia=current_date WHERE identificador=:id"
            ),
            {"id": actual["identificador"]},
        )
    fila = (
        (
            sesion.execute(
                text("""
        INSERT INTO perfil_capacidad_atencion
          (identificador_organizacion,dias_por_semana,horas_por_dia,porcentaje_ocupacion,ocupacion_confirmada,revision)
        VALUES (:o,:dias,:horas,:ocupacion,:confirmada,:revision_nueva)
        RETURNING identificador,dias_por_semana,horas_por_dia,porcentaje_ocupacion,ocupacion_confirmada,fecha_inicio_vigencia,revision
    """),
                {
                    "o": contexto.organizacion,
                    "dias": entrada.dias_por_semana,
                    "horas": entrada.horas_por_dia,
                    "ocupacion": entrada.porcentaje_ocupacion,
                    "confirmada": entrada.ocupacion_confirmada,
                    # Cada guardado crea una fila nueva; su revisión debe continuar la de la anterior.
                    "revision_nueva": int(actual["revision"]) + 1 if actual is not None else 0,
                },
            )
        )
        .mappings()
        .one()
    )
    sesion.execute(
        text(
            "UPDATE tratamiento SET estado='CAMBIOS_POR_REVISAR' WHERE identificador_organizacion=:o AND estado='CALCULADO'"
        ),
        {"o": contexto.organizacion},
    )
    return limpiar_json(dict(fila))


@router.get("/periodicidades-pago")
def periodicidades(sesion: Session = Depends(obtener_sesion_protegida)) -> dict:
    filas = (
        (
            sesion.execute(
                text("SELECT codigo,nombre,factor_mensual FROM periodicidad_pago ORDER BY orden")
            )
        )
        .mappings()
        .all()
    )
    return {"elementos": [limpiar_json(dict(f)) for f in filas]}


def _gasto_a_json(fila: Any) -> dict:
    """Un gasto con su equivalente mensual exacto (redondeado a centavos para mostrarlo)."""
    gasto = dict(fila)
    gasto["equivalente_mensual"] = equivalente_mensual(
        Decimal(gasto["importe_pagado_por_periodo"]), gasto["codigo_periodicidad"]
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return limpiar_json(gasto)


@router.get("/gastos")
def listar_gastos(
    limite: int = Query(default=20, ge=1, le=100),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    filas = (
        (
            sesion.execute(
                text("""
        SELECT g.identificador,g.nombre,g.categoria::text categoria,g.importe_pagado_por_periodo,
               g.codigo_periodicidad,g.fecha_inicio_vigencia,g.activo,g.revision
        FROM gasto_registrado g
        WHERE g.identificador_organizacion=:o ORDER BY g.fecha_hora_creacion DESC,g.identificador DESC LIMIT :limite
    """),
                {"o": contexto.organizacion, "limite": limite},
            )
        )
        .mappings()
        .all()
    )
    elementos = [_gasto_a_json(f) for f in filas]
    return {"elementos": elementos, "siguiente_cursor": None}


@router.post("/gastos", status_code=status.HTTP_201_CREATED)
def crear_gasto(
    entrada: GastoEntrada,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    fila = (
        (
            sesion.execute(
                text("""
        INSERT INTO gasto_registrado (identificador_organizacion,nombre,categoria,importe_pagado_por_periodo,codigo_periodicidad,fecha_inicio_vigencia,activo)
        VALUES (:o,:nombre,:categoria,:importe,:periodicidad,:fecha,:activo)
        RETURNING identificador,nombre,categoria::text categoria,importe_pagado_por_periodo,codigo_periodicidad,fecha_inicio_vigencia,activo,revision
    """),
                {
                    "o": contexto.organizacion,
                    "nombre": entrada.nombre,
                    "categoria": entrada.categoria,
                    "importe": entrada.importe_pagado_por_periodo,
                    "periodicidad": entrada.codigo_periodicidad,
                    "fecha": entrada.fecha_inicio_vigencia,
                    "activo": entrada.activo,
                },
            )
        )
        .mappings()
        .one()
    )
    sesion.execute(
        text(
            "UPDATE tratamiento SET estado='CAMBIOS_POR_REVISAR' WHERE identificador_organizacion=:o AND estado='CALCULADO'"
        ),
        {"o": contexto.organizacion},
    )
    return _gasto_a_json(fila)


@router.patch("/gastos/{identificador}")
def actualizar_gasto(
    identificador: UUID,
    entrada: GastoEntrada,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    revision = exigir_revision(if_match)
    fila = (
        (
            sesion.execute(
                text("""
        UPDATE gasto_registrado SET nombre=:nombre,categoria=:categoria,importe_pagado_por_periodo=:importe,
          codigo_periodicidad=:periodicidad,fecha_inicio_vigencia=:fecha,activo=:activo,revision=revision+1
        WHERE identificador=:id AND identificador_organizacion=:o AND revision=:revision
        RETURNING identificador,nombre,categoria::text categoria,importe_pagado_por_periodo,codigo_periodicidad,fecha_inicio_vigencia,activo,revision
    """),
                {
                    "nombre": entrada.nombre,
                    "categoria": entrada.categoria,
                    "importe": entrada.importe_pagado_por_periodo,
                    "periodicidad": entrada.codigo_periodicidad,
                    "fecha": entrada.fecha_inicio_vigencia,
                    "activo": entrada.activo,
                    "id": identificador,
                    "o": contexto.organizacion,
                    "revision": revision,
                },
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        actual = sesion.scalar(
            text(
                "SELECT revision FROM gasto_registrado WHERE identificador=:id AND identificador_organizacion=:o"
            ),
            {"id": identificador, "o": contexto.organizacion},
        )
        if actual is None:
            raise no_encontrado()
        raise conflicto_revision(int(actual))
    sesion.execute(
        text(
            "UPDATE tratamiento SET estado='CAMBIOS_POR_REVISAR' WHERE identificador_organizacion=:o AND estado='CALCULADO'"
        ),
        {"o": contexto.organizacion},
    )
    return _gasto_a_json(fila)


@router.delete("/gastos/{identificador}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_gasto(
    identificador: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> Response:
    revision = exigir_revision(if_match)
    eliminado = sesion.scalar(
        text(
            "DELETE FROM gasto_registrado WHERE identificador=:id AND identificador_organizacion=:o AND revision=:revision RETURNING identificador"
        ),
        {"id": identificador, "o": contexto.organizacion, "revision": revision},
    )
    if eliminado is None:
        actual = sesion.scalar(
            text(
                "SELECT revision FROM gasto_registrado WHERE identificador=:id AND identificador_organizacion=:o"
            ),
            {"id": identificador, "o": contexto.organizacion},
        )
        if actual is None:
            raise no_encontrado()
        raise conflicto_revision(int(actual))
    sesion.execute(
        text(
            "UPDATE tratamiento SET estado='CAMBIOS_POR_REVISAR' WHERE identificador_organizacion=:o AND estado='CALCULADO'"
        ),
        {"o": contexto.organizacion},
    )
    return Response(status_code=204)


@router.get("/equipos")
def listar_equipos(
    limite: int = Query(default=20, ge=1, le=100),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    filas = (
        (
            sesion.execute(
                text(
                    "SELECT identificador,nombre,precio_adquisicion,valor_residual,vida_util_anios,fecha_alta_en_servicio,estado::text estado,depreciacion_mensual,revision FROM equipo_o_instalacion_depreciable WHERE identificador_organizacion=:o ORDER BY fecha_hora_creacion DESC LIMIT :limite"
                ),
                {"o": contexto.organizacion, "limite": limite},
            )
        )
        .mappings()
        .all()
    )
    return {"elementos": [limpiar_json(dict(f)) for f in filas], "siguiente_cursor": None}


@router.post("/equipos", status_code=status.HTTP_201_CREATED)
def crear_equipo(
    entrada: EquipoEntrada,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    fila = (
        (
            sesion.execute(
                text("""
        INSERT INTO equipo_o_instalacion_depreciable (identificador_organizacion,nombre,precio_adquisicion,valor_residual,vida_util_anios,fecha_alta_en_servicio,estado)
        VALUES (:o,:nombre,:precio,:residual,:vida,:fecha,:estado)
        RETURNING identificador,nombre,precio_adquisicion,valor_residual,vida_util_anios,fecha_alta_en_servicio,estado::text estado,depreciacion_mensual,revision
    """),
                {
                    "o": contexto.organizacion,
                    "nombre": entrada.nombre,
                    "precio": entrada.precio_adquisicion,
                    "residual": entrada.valor_residual,
                    "vida": entrada.vida_util_anios,
                    "fecha": entrada.fecha_alta_en_servicio,
                    "estado": entrada.estado,
                },
            )
        )
        .mappings()
        .one()
    )
    sesion.execute(
        text(
            "UPDATE tratamiento SET estado='CAMBIOS_POR_REVISAR' WHERE identificador_organizacion=:o AND estado='CALCULADO'"
        ),
        {"o": contexto.organizacion},
    )
    return limpiar_json(dict(fila))


@router.patch("/equipos/{identificador}")
def actualizar_equipo(
    identificador: UUID,
    entrada: EquipoEntrada,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    revision = exigir_revision(if_match)
    fila = (
        (
            sesion.execute(
                text(
                    """UPDATE equipo_o_instalacion_depreciable SET nombre=:nombre,precio_adquisicion=:precio,valor_residual=:residual,vida_util_anios=:vida,fecha_alta_en_servicio=:fecha,estado=:estado,revision=revision+1 WHERE identificador=:id AND identificador_organizacion=:o AND revision=:revision RETURNING identificador,nombre,precio_adquisicion,valor_residual,vida_util_anios,fecha_alta_en_servicio,estado::text estado,depreciacion_mensual,revision"""
                ),
                {
                    "nombre": entrada.nombre,
                    "precio": entrada.precio_adquisicion,
                    "residual": entrada.valor_residual,
                    "vida": entrada.vida_util_anios,
                    "fecha": entrada.fecha_alta_en_servicio,
                    "estado": entrada.estado,
                    "id": identificador,
                    "o": contexto.organizacion,
                    "revision": revision,
                },
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        actual = sesion.scalar(
            text(
                "SELECT revision FROM equipo_o_instalacion_depreciable WHERE identificador=:id AND identificador_organizacion=:o"
            ),
            {"id": identificador, "o": contexto.organizacion},
        )
        if actual is None:
            raise no_encontrado()
        raise conflicto_revision(int(actual))
    sesion.execute(
        text(
            "UPDATE tratamiento SET estado='CAMBIOS_POR_REVISAR' WHERE identificador_organizacion=:o AND estado='CALCULADO'"
        ),
        {"o": contexto.organizacion},
    )
    return limpiar_json(dict(fila))


@router.delete("/equipos/{identificador}", status_code=204)
def eliminar_equipo(
    identificador: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> Response:
    revision = exigir_revision(if_match)
    eliminado = sesion.scalar(
        text(
            "DELETE FROM equipo_o_instalacion_depreciable WHERE identificador=:id AND identificador_organizacion=:o AND revision=:revision RETURNING identificador"
        ),
        {"id": identificador, "o": contexto.organizacion, "revision": revision},
    )
    if eliminado is None:
        actual = sesion.scalar(
            text(
                "SELECT revision FROM equipo_o_instalacion_depreciable WHERE identificador=:id AND identificador_organizacion=:o"
            ),
            {"id": identificador, "o": contexto.organizacion},
        )
        if actual is None:
            raise no_encontrado()
        raise conflicto_revision(int(actual))
    sesion.execute(
        text(
            "UPDATE tratamiento SET estado='CAMBIOS_POR_REVISAR' WHERE identificador_organizacion=:o AND estado='CALCULADO'"
        ),
        {"o": contexto.organizacion},
    )
    return Response(status_code=204)


@router.get("/costos-indirectos/resumen")
def resumen_costos(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    fijos, variables = RepositorioGastosSQLAlchemy(sesion).totales_mensuales(contexto.organizacion)
    depreciacion = RepositorioEquiposSQLAlchemy(sesion).depreciacion_mensual(contexto.organizacion)
    capacidad = (
        (
            sesion.execute(
                text(
                    "SELECT dias_por_semana,horas_por_dia,porcentaje_ocupacion FROM perfil_capacidad_atencion WHERE identificador_organizacion=:o AND fecha_fin_vigencia IS NULL"
                ),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    total = fijos + variables + depreciacion
    disponibles = efectivos = None
    if capacidad:
        disponibles = int(
            (
                Decimal(capacidad["dias_por_semana"])
                * Decimal(52)
                / Decimal(12)
                * Decimal(capacidad["horas_por_dia"])
                * Decimal(60)
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        efectivos = int(
            (
                Decimal(disponibles) * Decimal(capacidad["porcentaje_ocupacion"]) / Decimal(100)
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    bloqueos = []
    if total <= 0:
        bloqueos.append(
            {
                "codigo": "SIN_COSTOS_INDIRECTOS_REGISTRADOS",
                "paso": 3,
                "mensaje": "Registra gastos de tu consultorio",
            }
        )
    if capacidad is None:
        bloqueos.append(
            {"codigo": "SIN_PERFIL_CAPACIDAD", "paso": 4, "mensaje": "Indica cuándo atiendes"}
        )
    elif efectivos == 0:
        bloqueos.append(
            {
                "codigo": "SIN_TIEMPO_ATENCION",
                "paso": 4,
                "mensaje": "Sin tiempo de atención para calcular — revisa la ocupación.",
            }
        )
    return limpiar_json(
        {
            "gastos_fijos": fijos,
            "gastos_variables": variables,
            "depreciacion": depreciacion,
            "total_mensual": total,
            "minutos_disponibles": disponibles,
            "minutos_efectivos": efectivos,
            "costo_por_minuto": (total / Decimal(efectivos)).quantize(
                Decimal("0.0000000001"), rounding=ROUND_HALF_UP
            )
            if efectivos
            else None,
            "aportes": [],
            "bloqueos": bloqueos,
        }
    )
