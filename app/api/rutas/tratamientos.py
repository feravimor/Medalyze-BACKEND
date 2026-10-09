from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencias import ContextoSolicitud, obtener_contexto, obtener_sesion_protegida
from app.api.esquemas import (
    ConfiguracionTratamientoEntrada,
    ImportarPlantillasEntrada,
    TratamientoEntrada,
    VincularMaterialEntrada,
)
from app.application.utilidades import exigir_revision, limpiar_json
from app.core.errores import ErrorAplicacion, conflicto_revision, no_encontrado
from app.infrastructure.idempotencia import buscar_respuesta, completar, reservar

router = APIRouter()


def _detalle(sesion: Session, contexto: ContextoSolicitud, identificador: UUID) -> dict:
    fila = (
        (
            sesion.execute(
                text("""
        SELECT t.identificador,t.nombre,t.especialidad,t.estado::text estado,t.revision,
               v.duracion_clinica,v.espaciado,v.metodo::text metodo_materiales,v.importe_materiales,v.ajuste_porcentaje,
               CASE WHEN h.identificador IS NULL THEN NULL ELSE jsonb_build_object(
                 'identificador_hoja',h.identificador,'costo_total',h.costo_total,'precio_sugerido',h.precio_sugerido,
                 'margen_porcentaje',h.margen_porcentaje,'fecha_creacion',h.fecha_hora_creacion) END ultimo_resultado
        FROM tratamiento t LEFT JOIN version_configuracion_tratamiento v ON v.identificador=t.identificador_version_vigente
        LEFT JOIN hoja_costos_tratamiento h ON h.identificador=t.identificador_hoja_vigente
        WHERE t.identificador=:id AND t.identificador_organizacion=:o
    """),
                {"id": identificador, "o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if fila is None:
        raise no_encontrado()
    receta: list[dict[str, Any]] = []
    if fila.get("metodo_materiales") == "RECETA_INSUMOS":
        filas_receta = (
            (
                sesion.execute(
                    text("""
            SELECT l.identificador_insumo,l.cantidad,l.merma_porcentaje,i.nombre
            FROM tratamiento t JOIN linea_receta_insumos_tratamiento l ON l.identificador_version_configuracion=t.identificador_version_vigente
            JOIN insumo_clinico i ON i.identificador=l.identificador_insumo WHERE t.identificador=:id
        """),
                    {"id": identificador},
                )
            )
            .mappings()
            .all()
        )
        receta = [dict(r) for r in filas_receta]
    resultado = dict(fila)
    resultado["receta"] = [limpiar_json(r) for r in receta]
    return limpiar_json(resultado)


@router.get("/plantillas-tratamiento")
def plantillas(
    especialidad: str | None = None,
    mis_areas: bool = False,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    filas = (
        (
            sesion.execute(
                text("""
        SELECT p.clave,p.nombre,p.clave_especialidad especialidad,p.duracion_clinica,
               coalesce((SELECT jsonb_agg(m.nombre_generico ORDER BY m.orden) FROM material_sugerido_plantilla m WHERE m.identificador_plantilla=p.identificador),'[]'::jsonb) materiales_sugeridos,
               EXISTS (SELECT 1 FROM tratamiento t WHERE t.identificador_organizacion=:o AND t.nombre=p.nombre) agregado
        FROM plantilla_tratamiento p WHERE p.activa AND (CAST(:especialidad AS text) IS NULL OR p.clave_especialidad=CAST(:especialidad AS text))
          AND (NOT CAST(:mis_areas AS boolean) OR EXISTS (SELECT 1 FROM especialidad_seleccionada_por_usuario eu JOIN especialidad_odontologica e ON e.identificador=eu.identificador_especialidad WHERE eu.identificador_usuario=:u AND e.clave=p.clave_especialidad))
        ORDER BY p.clave LIMIT 100
    """),
                {
                    "o": contexto.organizacion,
                    "u": contexto.usuario,
                    "especialidad": especialidad,
                    "mis_areas": mis_areas,
                },
            )
        )
        .mappings()
        .all()
    )
    return {"elementos": [limpiar_json(dict(f)) for f in filas]}


@router.post("/tratamientos/importar-plantillas", status_code=201)
def importar_plantillas(
    entrada: ImportarPlantillasEntrada,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    creados = []
    for clave in entrada.claves:
        plantilla = (
            (
                sesion.execute(
                    text(
                        "SELECT * FROM plantilla_tratamiento WHERE clave=:clave AND version_catalogo=:version AND activa"
                    ),
                    {"clave": clave, "version": entrada.version_catalogo},
                )
            )
            .mappings()
            .first()
        )
        if plantilla is None:
            continue
        existente = sesion.scalar(
            text(
                "SELECT identificador FROM tratamiento WHERE identificador_organizacion=:o AND nombre=:nombre"
            ),
            {"o": contexto.organizacion, "nombre": plantilla["nombre"]},
        )
        if existente:
            creados.append(_detalle(sesion, contexto, existente))
            continue
        tratamiento = sesion.scalar(
            text(
                "INSERT INTO tratamiento (identificador_organizacion,nombre,especialidad) VALUES (:o,:nombre,:especialidad) RETURNING identificador"
            ),
            {
                "o": contexto.organizacion,
                "nombre": plantilla["nombre"],
                "especialidad": plantilla["clave_especialidad"],
            },
        )
        version = sesion.scalar(
            text(
                """INSERT INTO version_configuracion_tratamiento (identificador_tratamiento,numero_version,nombre,especialidad,duracion_clinica,espaciado,metodo,ajuste_porcentaje) VALUES (:t,1,:nombre,:especialidad,:duracion,NULL,NULL,1) RETURNING identificador"""
            ),
            {
                "t": tratamiento,
                "nombre": plantilla["nombre"],
                "especialidad": plantilla["clave_especialidad"],
                "duracion": plantilla["duracion_clinica"],
            },
        )
        sesion.execute(
            text("UPDATE tratamiento SET identificador_version_vigente=:v WHERE identificador=:t"),
            {"v": version, "t": tratamiento},
        )
        sesion.execute(
            text(
                """INSERT INTO material_sugerido_tratamiento (identificador_tratamiento,nombre_generico) SELECT :t,nombre_generico FROM material_sugerido_plantilla WHERE identificador_plantilla=:p ON CONFLICT DO NOTHING"""
            ),
            {"t": tratamiento, "p": plantilla["identificador"]},
        )
        creados.append(_detalle(sesion, contexto, tratamiento))
    return {"elementos": creados}


@router.get("/tratamientos")
def listar_tratamientos(
    estado: str | None = None,
    archivados: bool = False,
    busqueda: str = "",
    limite: int = Query(default=20, ge=1, le=100),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    filas = (
        (
            sesion.execute(
                text("""
        SELECT t.identificador,t.nombre,t.especialidad,t.estado::text estado,t.revision,v.duracion_clinica,
               CASE WHEN h.identificador IS NULL THEN NULL ELSE jsonb_build_object('costo_total',h.costo_total,'precio_sugerido',h.precio_sugerido,'margen_porcentaje',h.margen_porcentaje) END ultimo_resultado
        FROM tratamiento t LEFT JOIN version_configuracion_tratamiento v ON v.identificador=t.identificador_version_vigente
        LEFT JOIN hoja_costos_tratamiento h ON h.identificador=t.identificador_hoja_vigente
        WHERE t.identificador_organizacion=:o AND (CAST(:archivados AS boolean) OR t.estado<>'ARCHIVADO')
          AND (CAST(:estado AS text) IS NULL OR t.estado::text=CAST(:estado AS text))
          AND (CAST(:busqueda AS text)='' OR t.nombre ILIKE '%'||CAST(:busqueda AS text)||'%')
        ORDER BY t.fecha_hora_creacion DESC LIMIT :limite
    """),
                {
                    "o": contexto.organizacion,
                    "archivados": archivados,
                    "estado": estado or None,  # "" (filtro vacío del cliente) = sin filtro
                    "busqueda": busqueda,
                    "limite": limite,
                },
            )
        )
        .mappings()
        .all()
    )
    return {"elementos": [limpiar_json(dict(f)) for f in filas], "siguiente_cursor": None}


@router.post("/tratamientos", status_code=201)
def crear_tratamiento(
    entrada: TratamientoEntrada,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    cuerpo = entrada.model_dump(mode="json")
    repetida = buscar_respuesta(
        sesion, contexto, "crear_tratamiento", idempotency_key, cuerpo
    )
    if repetida:
        return repetida[1]
    if not reservar(sesion, contexto, "crear_tratamiento", idempotency_key, cuerpo):
        # Otra solicitud con la misma clave ganó la carrera (doble clic / reintento): repetir su respuesta.
        repetida = buscar_respuesta(sesion, contexto, "crear_tratamiento", idempotency_key, cuerpo)
        if repetida:
            return repetida[1]
        raise ErrorAplicacion(
            "CONFLICTO_REVISION", "La operación con esta clave sigue en proceso.", 409
        )
    tratamiento = sesion.scalar(
        text(
            "INSERT INTO tratamiento (identificador_organizacion,nombre,especialidad) VALUES (:o,:nombre,:especialidad) RETURNING identificador"
        ),
        {
            "o": contexto.organizacion,
            "nombre": entrada.nombre,
            "especialidad": entrada.especialidad,
        },
    )
    version = sesion.scalar(
        text(
            """INSERT INTO version_configuracion_tratamiento (identificador_tratamiento,numero_version,nombre,especialidad,duracion_clinica,ajuste_porcentaje) VALUES (:t,1,:nombre,:especialidad,:duracion,1) RETURNING identificador"""
        ),
        {
            "t": tratamiento,
            "nombre": entrada.nombre,
            "especialidad": entrada.especialidad,
            "duracion": entrada.duracion_clinica,
        },
    )
    sesion.execute(
        text("UPDATE tratamiento SET identificador_version_vigente=:v WHERE identificador=:t"),
        {"v": version, "t": tratamiento},
    )
    respuesta = _detalle(sesion, contexto, tratamiento)
    completar(sesion, contexto, "crear_tratamiento", idempotency_key, 201, respuesta)
    return respuesta


@router.get("/tratamientos/materiales-sugeridos")
def materiales_sugeridos(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    filas = (
        (
            sesion.execute(
                text("""
        SELECT m.nombre_generico,count(*) numero_tratamientos,jsonb_agg(m.identificador_tratamiento) identificadores_tratamientos
        FROM material_sugerido_tratamiento m JOIN tratamiento t ON t.identificador=m.identificador_tratamiento
        WHERE t.identificador_organizacion=:o AND t.estado='BORRADOR' AND m.identificador_insumo IS NULL
        GROUP BY m.nombre_generico ORDER BY m.nombre_generico
    """),
                {"o": contexto.organizacion},
            )
        )
        .mappings()
        .all()
    )
    return {"elementos": [limpiar_json(dict(f)) for f in filas]}


@router.post("/tratamientos/materiales-sugeridos/vincular")
def vincular_material(
    entrada: VincularMaterialEntrada,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    insumo = sesion.scalar(
        text(
            "SELECT identificador FROM insumo_clinico WHERE identificador=:i AND identificador_organizacion=:o AND fecha_hora_archivado IS NULL"
        ),
        {"i": entrada.identificador_insumo, "o": contexto.organizacion},
    )
    if insumo is None:
        raise ErrorAplicacion("ERROR_VALIDACION", "El insumo no es válido o está archivado.", 422)
    actualizados = 0
    for item in entrada.cantidades:
        tratamiento = sesion.scalar(
            text(
                "SELECT identificador FROM tratamiento WHERE identificador=:t AND identificador_organizacion=:o"
            ),
            {"t": item.identificador_tratamiento, "o": contexto.organizacion},
        )
        if tratamiento is None:
            continue
        sesion.execute(
            text(
                """UPDATE material_sugerido_tratamiento SET identificador_insumo=:i,cantidad=:cantidad WHERE identificador_tratamiento=:t AND nombre_generico=:nombre"""
            ),
            {
                "i": entrada.identificador_insumo,
                "cantidad": item.cantidad,
                "t": tratamiento,
                "nombre": entrada.nombre_generico,
            },
        )
        actualizados += 1
    return {"tratamientos_actualizados": actualizados}


@router.get("/tratamientos/{identificador}")
def detalle_tratamiento(
    identificador: UUID,
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    return _detalle(sesion, contexto, identificador)


@router.put("/tratamientos/{identificador}/configuracion")
def guardar_configuracion(
    identificador: UUID,
    entrada: ConfiguracionTratamientoEntrada,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    revision = exigir_revision(if_match)
    tratamiento = (
        (
            sesion.execute(
                text(
                    "SELECT identificador,revision FROM tratamiento WHERE identificador=:id AND identificador_organizacion=:o FOR UPDATE"
                ),
                {"id": identificador, "o": contexto.organizacion},
            )
        )
        .mappings()
        .first()
    )
    if tratamiento is None:
        raise no_encontrado()
    if tratamiento["revision"] != revision:
        raise conflicto_revision(int(tratamiento["revision"]))
    numero = sesion.scalar(
        text(
            "SELECT coalesce(max(numero_version),0)+1 FROM version_configuracion_tratamiento WHERE identificador_tratamiento=:t"
        ),
        {"t": identificador},
    )
    version = sesion.scalar(
        text("""
        INSERT INTO version_configuracion_tratamiento (identificador_tratamiento,numero_version,nombre,especialidad,duracion_clinica,espaciado,metodo,importe_materiales,ajuste_porcentaje)
        VALUES (:t,:numero,:nombre,:especialidad,:duracion,:espaciado,:metodo,:importe,:ajuste) RETURNING identificador
    """),
        {
            "t": identificador,
            "numero": numero,
            "nombre": entrada.nombre,
            "especialidad": entrada.especialidad,
            "duracion": entrada.duracion_clinica,
            "espaciado": entrada.espaciado,
            "metodo": entrada.metodo_materiales,
            "importe": entrada.importe_materiales,
            "ajuste": entrada.ajuste_porcentaje,
        },
    )
    for linea in entrada.receta:
        insumo = sesion.scalar(
            text(
                "SELECT 1 FROM insumo_clinico WHERE identificador=:i AND identificador_organizacion=:o AND fecha_hora_archivado IS NULL"
            ),
            {"i": linea.identificador_insumo, "o": contexto.organizacion},
        )
        if not insumo:
            raise ErrorAplicacion("ERROR_VALIDACION", "La receta contiene un insumo inválido.", 422)
        sesion.execute(
            text(
                "INSERT INTO linea_receta_insumos_tratamiento (identificador_version_configuracion,identificador_insumo,cantidad,merma_porcentaje) VALUES (:v,:i,:cantidad,:merma)"
            ),
            {
                "v": version,
                "i": linea.identificador_insumo,
                "cantidad": linea.cantidad,
                "merma": linea.merma_porcentaje,
            },
        )
    nuevo_estado = (
        "CAMBIOS_POR_REVISAR"
        if sesion.scalar(
            text(
                "SELECT identificador_hoja_vigente IS NOT NULL FROM tratamiento WHERE identificador=:t"
            ),
            {"t": identificador},
        )
        else "BORRADOR"
    )
    sesion.execute(
        text(
            "UPDATE tratamiento SET nombre=:nombre,especialidad=:especialidad,identificador_version_vigente=:v,estado=:estado,revision=revision+1 WHERE identificador=:t"
        ),
        {
            "nombre": entrada.nombre,
            "especialidad": entrada.especialidad,
            "v": version,
            "estado": nuevo_estado,
            "t": identificador,
        },
    )
    return _detalle(sesion, contexto, identificador)


def _cambiar_estado(
    identificador: UUID,
    estado: str,
    revision: int,
    contexto: ContextoSolicitud,
    sesion: Session,
) -> dict:
    fila = sesion.scalar(
        text(
            "UPDATE tratamiento SET estado=CAST(:estado AS estado_tratamiento),fecha_hora_archivado=CASE WHEN :archivar THEN now() ELSE NULL END,revision=revision+1 WHERE identificador=:id AND identificador_organizacion=:o AND revision=:revision RETURNING identificador"
        ),
        {
            "estado": estado,
            "archivar": estado == "ARCHIVADO",
            "id": identificador,
            "o": contexto.organizacion,
            "revision": revision,
        },
    )
    if fila is None:
        actual = sesion.scalar(
            text(
                "SELECT revision FROM tratamiento WHERE identificador=:id AND identificador_organizacion=:o"
            ),
            {"id": identificador, "o": contexto.organizacion},
        )
        if actual is None:
            raise no_encontrado()
        raise conflicto_revision(int(actual))
    return _detalle(sesion, contexto, identificador)


@router.post("/tratamientos/{identificador}/archivar")
def archivar_tratamiento(
    identificador: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    return _cambiar_estado(
        identificador, "ARCHIVADO", exigir_revision(if_match), contexto, sesion
    )


@router.post("/tratamientos/{identificador}/restaurar")
def restaurar_tratamiento(
    identificador: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida),
) -> dict:
    tiene_hoja = sesion.scalar(
        text(
            "SELECT identificador_hoja_vigente IS NOT NULL FROM tratamiento WHERE identificador=:id AND identificador_organizacion=:o"
        ),
        {"id": identificador, "o": contexto.organizacion},
    )
    return _cambiar_estado(
        identificador,
        # Mientras está ARCHIVADO el tratamiento queda fuera de la marca CAMBIOS_POR_REVISAR (que solo
        # se aplica a los CALCULADO). Al restaurar no se puede saber si el precio sigue vigente, así
        # que se pide revisarlo en vez de mostrarlo como actual.
        "CAMBIOS_POR_REVISAR" if tiene_hoja else "BORRADOR",
        exigir_revision(if_match),
        contexto,
        sesion,
    )
