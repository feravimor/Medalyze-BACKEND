from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencias import ContextoSolicitud, obtener_contexto, obtener_sesion_protegida
from app.api.esquemas import CalculoEntrada, ConfiguracionTratamientoEntrada, VistaPreviaEntrada
from app.application.utilidades import limpiar_json
from app.core.errores import ErrorAplicacion, conflicto_revision, no_encontrado
from app.domain.costeo import EntradaCosteo, ResultadoCosteo, calcular_costeo
from app.infrastructure.idempotencia import buscar_respuesta, completar, reservar

router = APIRouter()


def _cargar_configuracion(
    sesion: Session, contexto: ContextoSolicitud, identificador: UUID
) -> tuple[dict, dict]:
    tratamiento = (
        (
            sesion.execute(
                text(
                    "SELECT * FROM tratamiento WHERE identificador=:id AND identificador_organizacion=:o"
                ),
                {"id": identificador, "o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if tratamiento is None:
        raise no_encontrado()
    config = (
        (
            sesion.execute(
                text("SELECT * FROM version_configuracion_tratamiento WHERE identificador=:v"),
                {"v": tratamiento["identificador_version_vigente"]},
            )
        )
        .mappings()
        .first()
    )
    if config is None:
        raise no_encontrado("El tratamiento no tiene configuración vigente.")
    return dict(tratamiento), dict(config)


def _materiales_receta(sesion: Session, version: UUID) -> tuple[Decimal, list[dict]]:
    filas = (
        (
            sesion.execute(
                text("""
        SELECT l.identificador_insumo,i.nombre,l.cantidad,l.merma_porcentaje,p.costo_unitario,
               l.cantidad*(1+l.merma_porcentaje/100)*p.costo_unitario subtotal
        FROM linea_receta_insumos_tratamiento l JOIN insumo_clinico i ON i.identificador=l.identificador_insumo
        JOIN LATERAL (SELECT costo_unitario FROM precio_historico_insumo WHERE identificador_insumo=i.identificador ORDER BY fecha_inicio_vigencia DESC,fecha_hora_creacion DESC LIMIT 1) p ON true
        WHERE l.identificador_version_configuracion=:v AND i.fecha_hora_archivado IS NULL
    """),
                {"v": version},
            )
        )
        .mappings()
        .all()
    )
    return sum((Decimal(f["subtotal"]) for f in filas), Decimal(0)), [dict(f) for f in filas]


def _promedio_materiales(
    sesion: Session, contexto: ContextoSolicitud
) -> tuple[Decimal | None, list[dict], str]:
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
        return None, [], "SIN_BASE"
    consumo = sum((Decimal(f["consumo_materiales"]) for f in filas), Decimal(0))
    tratamientos = sum(int(f["tratamientos_atendidos"]) for f in filas)
    madurez = "INICIAL" if len(filas) == 1 else "EN_FORMACION" if len(filas) == 2 else "MADURA"
    return consumo / Decimal(tratamientos), [dict(f) for f in filas], madurez


def _calcular(
    sesion: Session,
    contexto: ContextoSolicitud,
    identificador: UUID,
    sobreescritura: ConfiguracionTratamientoEntrada | None = None,
) -> tuple[ResultadoCosteo, dict]:
    tratamiento, config = _cargar_configuracion(sesion, contexto, identificador)
    if sobreescritura:
        config.update(sobreescritura.model_dump())
        config["metodo"] = config.pop("metodo_materiales")
    gastos = (
        (
            sesion.execute(
                text(
                    """SELECT coalesce(sum(CASE WHEN g.categoria='FIJO' THEN g.importe_pagado_por_periodo*p.factor_mensual ELSE 0 END),0) fijos,coalesce(sum(CASE WHEN g.categoria='VARIABLE' THEN g.importe_pagado_por_periodo*p.factor_mensual ELSE 0 END),0) variables FROM gasto_registrado g JOIN periodicidad_pago p ON p.codigo=g.codigo_periodicidad WHERE g.identificador_organizacion=:o AND g.activo AND g.fecha_inicio_vigencia<=current_date AND (g.fecha_fin_vigencia IS NULL OR g.fecha_fin_vigencia>=current_date)"""
                ),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .one()
    )
    depreciacion = Decimal(
        sesion.scalar(
            text(
                "SELECT coalesce(sum(depreciacion_mensual),0) FROM equipo_o_instalacion_depreciable WHERE identificador_organizacion=:o AND estado='ACTIVO' AND (fecha_alta_en_servicio IS NULL OR fecha_alta_en_servicio<=current_date)"
            ),
            {"o": contexto.organizacion},
        )
        or 0
    )
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
    organizacion = (
        (
            sesion.execute(
                text(
                    "SELECT multiplo_redondeo,espaciado_por_defecto FROM organizacion_consultorio WHERE identificador=:o"
                ),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .one()
    )
    espaciado = config.get("espaciado")
    if espaciado is None:
        espaciado = (
            organizacion["espaciado_por_defecto"]
            if organizacion["espaciado_por_defecto"] is not None
            else 10
        )
    metodo = config.get("metodo")
    materiales = None
    lineas: list[dict] = []
    periodos: list[dict] = []
    madurez = "SIN_BASE"
    if metodo == "IMPORTE_RAPIDO":
        materiales = config.get("importe_materiales")
    elif metodo == "RECETA_INSUMOS":
        if sobreescritura:
            materiales = Decimal(0)
            for linea in sobreescritura.receta:
                precio = sesion.scalar(
                    text(
                        """SELECT p.costo_unitario FROM insumo_clinico i JOIN LATERAL (SELECT costo_unitario FROM precio_historico_insumo WHERE identificador_insumo=i.identificador ORDER BY fecha_inicio_vigencia DESC,fecha_hora_creacion DESC LIMIT 1) p ON true WHERE i.identificador=:i AND i.identificador_organizacion=:o AND i.fecha_hora_archivado IS NULL"""
                    ),
                    {"i": linea.identificador_insumo, "o": contexto.organizacion},
                )
                if precio is not None:
                    materiales += (
                        linea.cantidad
                        * (Decimal(1) + linea.merma_porcentaje / Decimal(100))
                        * Decimal(precio)
                    )
        else:
            materiales, lineas = _materiales_receta(sesion, config["identificador"])
    elif metodo == "PROMEDIO_MENSUAL":
        materiales, periodos, madurez = _promedio_materiales(sesion, contexto)
    entrada = EntradaCosteo(
        gastos_fijos=Decimal(gastos["fijos"]),
        gastos_variables=Decimal(gastos["variables"]),
        depreciacion=depreciacion,
        dias_por_semana=int(capacidad["dias_por_semana"]) if capacidad else None,
        horas_por_dia=Decimal(capacidad["horas_por_dia"]) if capacidad else None,
        porcentaje_ocupacion=Decimal(capacidad["porcentaje_ocupacion"]) if capacidad else None,
        duracion_clinica=int(config["duracion_clinica"]),
        espaciado=int(espaciado),
        metodo_materiales=metodo,
        materiales_generales=Decimal(materiales) if materiales is not None else None,
        materiales_especiales=Decimal(0),
        ajuste_porcentaje=Decimal(config.get("ajuste_porcentaje") or 1),
        multiplo_redondeo=Decimal(organizacion["multiplo_redondeo"]),
    )
    return calcular_costeo(entrada), {
        "tratamiento": tratamiento,
        "config": config,
        "entrada": entrada,
        "lineas": lineas,
        "periodos": periodos,
        "madurez": madurez,
    }


def _respuesta_resultado(resultado: ResultadoCosteo) -> dict:
    bloqueos = [
        {"codigo": b.codigo.value, "paso": b.paso, "mensaje": b.mensaje, "campo": b.campo}
        for b in resultado.bloqueos
    ]
    if not resultado.completo:
        return limpiar_json({"estado": "borrador", "resultado": None, "bloqueos": bloqueos})
    return limpiar_json(
        {
            "estado": "completo",
            "resultado": {
                "costo_tiempo": resultado.costo_tiempo,
                "materiales_generales": resultado.materiales_generales,
                "materiales_especiales": resultado.materiales_especiales,
                "costo_total": resultado.costo_total,
                "importe_ajustado": resultado.importe_ajustado,
                "precio_sugerido": resultado.precio_sugerido,
                "margen_porcentaje": resultado.margen_porcentaje,
                "semaforo": resultado.semaforo,
            },
            "bloqueos": [],
        }
    )


@router.post("/tratamientos/{identificador}/vista-previa")
def vista_previa(
    identificador: UUID,
    entrada: VistaPreviaEntrada,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    resultado, _ = _calcular(sesion, contexto, identificador, entrada.configuracion)
    return _respuesta_resultado(resultado)


@router.post("/tratamientos/{identificador}/calculos", status_code=201)
def emitir_calculo(
    identificador: UUID,
    entrada: CalculoEntrada,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    if if_match is None or int(if_match.strip('"')) != entrada.revision_tratamiento:
        raise ErrorAplicacion(
            "REVISION_REQUERIDA", "La revisión del encabezado y el cuerpo debe coincidir.", 428
        )
    cuerpo = entrada.model_dump(mode="json")
    repetida = buscar_respuesta(
        sesion, contexto, f"calcular:{identificador}", idempotency_key, cuerpo
    )
    if repetida:
        return repetida[1]
    reservar(sesion, contexto, f"calcular:{identificador}", idempotency_key, cuerpo)
    resultado, datos = _calcular(sesion, contexto, identificador)
    tratamiento = datos["tratamiento"]
    if int(tratamiento["revision"]) != entrada.revision_tratamiento:
        raise conflicto_revision(int(tratamiento["revision"]))
    if not resultado.completo:
        bloqueos = [
            {"codigo": b.codigo.value, "paso": b.paso, "mensaje": b.mensaje, "campo": b.campo}
            for b in resultado.bloqueos
        ]
        raise ErrorAplicacion(
            "CALCULO_BLOQUEADO",
            "Faltan datos para calcular el costo del tratamiento.",
            422,
            bloqueos=bloqueos,
        )
    e = datos["entrada"]
    hoja = sesion.scalar(
        text("""
        INSERT INTO hoja_costos_tratamiento
          (identificador_organizacion,identificador_tratamiento,identificador_version_configuracion,sustituye_a,
           gastos_fijos,gastos_variables,depreciacion,pool_mensual,minutos_disponibles,minutos_efectivos,costo_por_minuto,
           minutos_imputados,costo_tiempo,materiales_generales,materiales_especiales,costo_total,ajuste_porcentaje,
           importe_ajustado,precio_sugerido,margen_porcentaje,semaforo,madurez)
        VALUES (:o,:t,:v,:anterior,:fijos,:variables,:depreciacion,:pool,:disponibles,:efectivos,:costo_minuto,
                :imputados,:tiempo,:mg,:me,:total,:ajuste,:importe,:precio,:margen,:semaforo,:madurez) RETURNING identificador
    """),
        {
            "o": contexto.organizacion,
            "t": identificador,
            "v": datos["config"]["identificador"],
            "anterior": tratamiento["identificador_hoja_vigente"],
            "fijos": e.gastos_fijos,
            "variables": e.gastos_variables,
            "depreciacion": e.depreciacion,
            "pool": resultado.pool_mensual,
            "disponibles": resultado.minutos_disponibles,
            "efectivos": resultado.minutos_efectivos,
            "costo_minuto": resultado.costo_por_minuto,
            "imputados": resultado.minutos_imputados,
            "tiempo": resultado.costo_tiempo,
            "mg": resultado.materiales_generales,
            "me": resultado.materiales_especiales,
            "total": resultado.costo_total,
            "ajuste": e.ajuste_porcentaje,
            "importe": resultado.importe_ajustado,
            "precio": resultado.precio_sugerido,
            "margen": resultado.margen_porcentaje,
            "semaforo": resultado.semaforo,
            "madurez": datos["madurez"],
        },
    )
    for linea in datos["lineas"]:
        sesion.execute(
            text(
                """INSERT INTO linea_insumo_hoja_costos (identificador_hoja,identificador_insumo,nombre_insumo,cantidad,costo_unitario,subtotal) VALUES (:h,:i,:nombre,:cantidad,:costo,:subtotal)"""
            ),
            {
                "h": hoja,
                "i": linea["identificador_insumo"],
                "nombre": linea["nombre"],
                "cantidad": linea["cantidad"],
                "costo": linea["costo_unitario"],
                "subtotal": linea["subtotal"],
            },
        )
    for periodo in datos["periodos"]:
        sesion.execute(
            text(
                """INSERT INTO periodo_mensual_hoja_costos (identificador_hoja,identificador_periodo,mes,consumo_materiales,tratamientos_atendidos,incluido) VALUES (:h,:p,:mes,:consumo,:tratamientos,true)"""
            ),
            {
                "h": hoja,
                "p": periodo["identificador"],
                "mes": periodo["mes"],
                "consumo": periodo["consumo_materiales"],
                "tratamientos": periodo["tratamientos_atendidos"],
            },
        )
    sesion.execute(
        text(
            "UPDATE tratamiento SET identificador_hoja_vigente=:h,estado='CALCULADO',revision=revision+1 WHERE identificador=:t"
        ),
        {"h": hoja, "t": identificador},
    )
    respuesta = _detalle_hoja(sesion, contexto, hoja)
    completar(sesion, contexto, f"calcular:{identificador}", idempotency_key, 201, respuesta)
    return respuesta


@router.get("/tratamientos/{identificador}/hojas-costos")
def historial(
    identificador: UUID,
    limite: int = Query(default=20, ge=1, le=100),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    existe = sesion.scalar(
        text("SELECT 1 FROM tratamiento WHERE identificador=:t AND identificador_organizacion=:o"),
        {"t": identificador, "o": contexto.organizacion},
    )
    if not existe:
        raise no_encontrado()
    filas = (
        (
            sesion.execute(
                text("""
        SELECT h.identificador,h.fecha_hora_creacion fecha_creacion,h.costo_total,h.precio_sugerido,h.margen_porcentaje,
               h.ajuste_porcentaje,v.metodo::text metodo_materiales,(t.identificador_hoja_vigente=h.identificador) vigente
        FROM hoja_costos_tratamiento h JOIN tratamiento t ON t.identificador=h.identificador_tratamiento
        JOIN version_configuracion_tratamiento v ON v.identificador=h.identificador_version_configuracion
        WHERE h.identificador_tratamiento=:t AND h.identificador_organizacion=:o
        ORDER BY h.fecha_hora_creacion DESC,h.identificador DESC LIMIT :limite
    """),
                {"t": identificador, "o": contexto.organizacion, "limite": limite},
            )
        )
        .mappings()
        .all()
    )
    return {"elementos": [limpiar_json(dict(f)) for f in filas], "siguiente_cursor": None}


def _detalle_hoja(
    sesion: Session, contexto: ContextoSolicitud, identificador: UUID
) -> dict:
    fila = (
        (
            sesion.execute(
                text(
                    "SELECT * FROM hoja_costos_tratamiento WHERE identificador=:id AND identificador_organizacion=:o"
                ),
                {"id": identificador, "o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        raise no_encontrado()
    lineas = (
        (
            sesion.execute(
                text(
                    "SELECT nombre_insumo,cantidad,costo_unitario,subtotal FROM linea_insumo_hoja_costos WHERE identificador_hoja=:h"
                ),
                {"h": identificador},
            )
        )
        .mappings()
        .all()
    )
    periodos = (
        (
            sesion.execute(
                text(
                    "SELECT mes,consumo_materiales,tratamientos_atendidos,incluido,motivo_exclusion::text FROM periodo_mensual_hoja_costos WHERE identificador_hoja=:h ORDER BY mes DESC"
                ),
                {"h": identificador},
            )
        )
        .mappings()
        .all()
    )
    resultado = dict(fila)
    resultado["lineas_insumo"] = [dict(x) for x in lineas]
    resultado["periodos"] = [dict(x) for x in periodos]
    return limpiar_json(resultado)


@router.get("/hojas-costos/{identificador}")
def detalle_hoja(
    identificador: UUID,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    return _detalle_hoja(sesion, contexto, identificador)
