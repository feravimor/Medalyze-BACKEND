from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencias import ContextoSolicitud, obtener_contexto, obtener_sesion_protegida
from app.api.esquemas import CorreccionPeriodoEntrada, PeriodoMensualEntrada
from app.application.utilidades import exigir_revision, limpiar_json
from app.core.errores import ErrorAplicacion, conflicto_revision, no_encontrado

router = APIRouter()


def _detalle(sesion: Session, contexto: ContextoSolicitud, identificador: UUID) -> dict:
    fila = (
        (
            sesion.execute(
                text("""
        SELECT p.identificador,p.mes,p.revision,v.identificador identificador_version,v.numero_version,
               v.tipo_movimiento::text tipo_movimiento,v.consumo_materiales,v.tratamientos_atendidos,
               v.procedencia::text procedencia,v.notas,
               CASE WHEN v.tipo_movimiento='ANULACION' THEN 'ANULADO' ELSE 'VIGENTE' END estado,
               CASE WHEN v.tratamientos_atendidos>0 THEN round(v.consumo_materiales/v.tratamientos_atendidos,2) END materiales_por_tratamiento
        FROM periodo_mensual_consumo p JOIN version_periodo_mensual_consumo v ON v.identificador=p.identificador_version_vigente
        WHERE p.identificador=:id AND p.identificador_organizacion=:o
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


@router.get("/periodos-mensuales")
def listar_periodos(
    limite: int = Query(default=20, ge=1, le=100),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    filas = (
        (
            sesion.execute(
                text("""
        SELECT p.identificador,p.mes,p.revision,v.numero_version,v.tipo_movimiento::text tipo_movimiento,
               v.consumo_materiales,v.tratamientos_atendidos,v.procedencia::text procedencia,v.notas,
               CASE WHEN v.tipo_movimiento='ANULACION' THEN 'ANULADO' ELSE 'VIGENTE' END estado,
               CASE WHEN v.tratamientos_atendidos>0 THEN round(v.consumo_materiales/v.tratamientos_atendidos,2) END materiales_por_tratamiento
        FROM periodo_mensual_consumo p JOIN version_periodo_mensual_consumo v ON v.identificador=p.identificador_version_vigente
        WHERE p.identificador_organizacion=:o ORDER BY p.mes DESC LIMIT :limite
    """),
                {"o": contexto.organizacion, "limite": limite},
            )
        )
        .mappings()
        .all()
    )
    return {"elementos": [limpiar_json(dict(f)) for f in filas], "siguiente_cursor": None}


@router.post("/periodos-mensuales", status_code=status.HTTP_201_CREATED)
def crear_periodo(
    entrada: PeriodoMensualEntrada,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    try:
        periodo = sesion.scalar(
            text(
                "INSERT INTO periodo_mensual_consumo (identificador_organizacion,mes) VALUES (:o,:mes) RETURNING identificador"
            ),
            {"o": contexto.organizacion, "mes": entrada.mes},
        )
    except IntegrityError as exc:
        raise ErrorAplicacion(
            "PERIODO_YA_REGISTRADO", "Ya existe información para este mes.", 409
        ) from exc
    version = sesion.scalar(
        text(
            """INSERT INTO version_periodo_mensual_consumo (identificador_periodo,numero_version,tipo_movimiento,consumo_materiales,tratamientos_atendidos,procedencia,notas) VALUES (:p,1,'CAPTURA_INICIAL',:consumo,:tratamientos,:procedencia,:notas) RETURNING identificador"""
        ),
        {
            "p": periodo,
            "consumo": entrada.consumo_materiales,
            "tratamientos": entrada.tratamientos_atendidos,
            "procedencia": entrada.procedencia,
            "notas": entrada.notas,
        },
    )
    sesion.execute(
        text(
            "UPDATE periodo_mensual_consumo SET identificador_version_vigente=:v WHERE identificador=:p"
        ),
        {"v": version, "p": periodo},
    )
    sesion.execute(
        text(
            "UPDATE tratamiento SET estado='CAMBIOS_POR_REVISAR' WHERE identificador_organizacion=:o AND estado='CALCULADO' AND EXISTS (SELECT 1 FROM version_configuracion_tratamiento c WHERE c.identificador=tratamiento.identificador_version_vigente AND c.metodo='PROMEDIO_MENSUAL')"
        ),
        {"o": contexto.organizacion},
    )
    return _detalle(sesion, contexto, periodo)


@router.get("/periodos-mensuales/promedio-materiales")
def promedio_materiales(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    filas = (
        (
            sesion.execute(
                text("""
        SELECT p.identificador,p.mes,v.consumo_materiales,v.tratamientos_atendidos
        FROM periodo_mensual_consumo p JOIN version_periodo_mensual_consumo v ON v.identificador=p.identificador_version_vigente
        WHERE p.identificador_organizacion=:o AND p.mes<=current_date AND v.tipo_movimiento<>'ANULACION' AND v.tratamientos_atendidos>0
        ORDER BY p.mes DESC LIMIT 3
    """),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .all()
    )
    if not filas:
        raise ErrorAplicacion(
            "CALCULO_BLOQUEADO",
            "No existen meses válidos para calcular el promedio.",
            422,
            bloqueos=[
                {
                    "codigo": "SIN_MESES_VALIDOS",
                    "paso": 6,
                    "mensaje": "Registra un mes con consumo y tratamientos atendidos",
                }
            ],
        )
    consumo = sum((Decimal(f["consumo_materiales"]) for f in filas), Decimal(0))
    tratamientos = sum(int(f["tratamientos_atendidos"]) for f in filas)
    madurez = "INICIAL" if len(filas) == 1 else "EN_FORMACION" if len(filas) == 2 else "MADURA"
    return limpiar_json(
        {
            "importe_por_tratamiento": (consumo / Decimal(tratamientos)).quantize(
                Decimal("0.0000000001"), rounding=ROUND_HALF_UP
            ),
            "madurez": madurez,
            "periodos_incluidos": [f["identificador"] for f in filas],
            "periodos_excluidos": [],
        }
    )


@router.get("/periodos-mensuales/{identificador}")
def detalle_periodo(
    identificador: UUID,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    return _detalle(sesion, contexto, identificador)


def _nueva_version(
    sesion: Session,
    contexto: ContextoSolicitud,
    identificador: UUID,
    revision: int,
    tipo: str,
    consumo: Decimal | None,
    tratamientos: int | None,
    procedencia: str | None,
    notas: str | None,
) -> dict:
    periodo = (
        (
            sesion.execute(
                text(
                    "SELECT identificador,identificador_version_vigente,revision FROM periodo_mensual_consumo WHERE identificador=:id AND identificador_organizacion=:o FOR UPDATE"
                ),
                {"id": identificador, "o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if periodo is None:
        raise no_encontrado()
    if periodo["revision"] != revision:
        raise conflicto_revision(int(periodo["revision"]))
    numero = sesion.scalar(
        text(
            "SELECT coalesce(max(numero_version),0)+1 FROM version_periodo_mensual_consumo WHERE identificador_periodo=:p"
        ),
        {"p": identificador},
    )
    version = sesion.scalar(
        text(
            """INSERT INTO version_periodo_mensual_consumo (identificador_periodo,numero_version,tipo_movimiento,identificador_version_sustituida,consumo_materiales,tratamientos_atendidos,procedencia,notas) VALUES (:p,:numero,:tipo,:anterior,:consumo,:tratamientos,:procedencia,:notas) RETURNING identificador"""
        ),
        {
            "p": identificador,
            "numero": numero,
            "tipo": tipo,
            "anterior": periodo["identificador_version_vigente"],
            "consumo": consumo,
            "tratamientos": tratamientos,
            "procedencia": procedencia,
            "notas": notas,
        },
    )
    sesion.execute(
        text(
            "UPDATE periodo_mensual_consumo SET identificador_version_vigente=:v,revision=revision+1 WHERE identificador=:p"
        ),
        {"v": version, "p": identificador},
    )
    sesion.execute(
        text(
            "UPDATE tratamiento SET estado='CAMBIOS_POR_REVISAR' WHERE identificador_organizacion=:o AND estado='CALCULADO' AND EXISTS (SELECT 1 FROM version_configuracion_tratamiento c WHERE c.identificador=tratamiento.identificador_version_vigente AND c.metodo='PROMEDIO_MENSUAL')"
        ),
        {"o": contexto.organizacion},
    )
    return _detalle(sesion, contexto, identificador)


@router.post("/periodos-mensuales/{identificador}/correcciones", status_code=201)
def corregir_periodo(
    identificador: UUID,
    entrada: CorreccionPeriodoEntrada,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    return _nueva_version(
        sesion,
        contexto,
        identificador,
        exigir_revision(if_match),
        "CORRECCION",
        entrada.consumo_materiales,
        entrada.tratamientos_atendidos,
        entrada.procedencia,
        entrada.notas,
    )


@router.post("/periodos-mensuales/{identificador}/anular")
def anular_periodo(
    identificador: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    return _nueva_version(
        sesion,
        contexto,
        identificador,
        exigir_revision(if_match),
        "ANULACION",
        None,
        None,
        None,
        "Sin datos actuales",
    )


@router.post("/periodos-mensuales/{identificador}/restaurar")
def restaurar_periodo(
    identificador: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    movimiento = sesion.scalar(
        text(
            "SELECT v.tipo_movimiento::text FROM periodo_mensual_consumo p JOIN version_periodo_mensual_consumo v ON v.identificador=p.identificador_version_vigente WHERE p.identificador=:id AND p.identificador_organizacion=:o"
        ),
        {"id": identificador, "o": contexto.organizacion},
    )
    if movimiento is None:
        raise no_encontrado()
    if movimiento != "ANULACION":
        raise ErrorAplicacion("ERROR_VALIDACION", "Este periodo no está anulado.", 422)
    anterior = (
        (
            sesion.execute(
                text(
                    """SELECT consumo_materiales,tratamientos_atendidos,procedencia::text procedencia,notas FROM version_periodo_mensual_consumo WHERE identificador_periodo=:p AND tipo_movimiento<>'ANULACION' ORDER BY numero_version DESC LIMIT 1"""
                ),
                {"p": identificador},
            )
        )
        .mappings()
        .first()
    )
    if anterior is None:
        raise no_encontrado("No existe una versión que pueda restaurarse.")
    return _nueva_version(
        sesion,
        contexto,
        identificador,
        exigir_revision(if_match),
        "RESTAURACION",
        anterior["consumo_materiales"],
        anterior["tratamientos_atendidos"],
        anterior["procedencia"],
        anterior["notas"],
    )
