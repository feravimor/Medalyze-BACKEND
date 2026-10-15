import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TypedDict
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencias import ContextoSolicitud, obtener_contexto, obtener_sesion_protegida
from app.api.esquemas import (
    CrearDemoEntrada,
    ListaEscenariosDemo,
    SesionDemo,
)
from app.api.rutas.autenticacion import _crear_sesion, _establecer_cookie, _respuesta_sesion
from app.core.database import fijar_contexto_organizacion, obtener_sesion
from app.core.errores import ErrorAplicacion, no_encontrado
from app.core.rate_limit import limitar_intentos
from app.core.seguridad import hash_contrasena

router = APIRouter()


Material = tuple[str, str, str, float | Decimal, int | float | Decimal]


class Scenario(TypedDict):
    nombre: str
    consultorio: str
    usuario: str
    tratamiento: str
    especialidad: str
    horas: int
    dias: int
    ocupacion: int
    duracion: int
    incremento: int
    precio: str
    insumos: int
    fijos: list[tuple[str, int]]
    variables: list[tuple[str, int]]
    equipo: int


SCENARIOS: dict[str, Scenario] = {
    "consulta": {
        "nombre": "Consulta",
        "consultorio": "DEMO Consulta",
        "usuario": "Usuario demo 1",
        "tratamiento": "Consulta de ortodoncia básica",
        "especialidad": "Ortodoncia",
        "horas": 5,
        "dias": 4,
        "ocupacion": 50,
        "duracion": 45,
        "incremento": 125,
        "precio": "650.00",
        "insumos": 15,
        "fijos": [("Renta", 4000), ("Asistente", 3500), ("Internet", 400), ("Contador", 400)],
        "variables": [
            ("Electricidad", 650),
            ("Agua", 150),
            ("Servicio de limpieza", 300),
            ("Mantenimiento", 200),
        ],
        "equipo": 48000,
    },
    "limpieza": {
        "nombre": "Limpieza",
        "consultorio": "DEMO Limpieza",
        "usuario": "Usuario demo 2",
        "tratamiento": "Profilaxis",
        "especialidad": "Odontología general y preventiva",
        "horas": 6,
        "dias": 4,
        "ocupacion": 60,
        "duracion": 45,
        "incremento": 325,
        "precio": "1200.00",
        "insumos": 18,
        "fijos": [("Renta", 6000), ("Asistente", 4500), ("Internet", 400), ("Contador", 500)],
        "variables": [
            ("Electricidad", 1000),
            ("Agua", 200),
            ("Servicio de limpieza", 500),
            ("Mantenimiento", 300),
        ],
        "equipo": 60000,
    },
    "resina": {
        "nombre": "Resina",
        "consultorio": "DEMO Resina",
        "usuario": "Usuario demo 3",
        "tratamiento": "Resina posteriores",
        "especialidad": "Odontología general y preventiva",
        "horas": 7,
        "dias": 4,
        "ocupacion": 65,
        "duracion": 60,
        "incremento": 200,
        "precio": "2550.00",
        "insumos": 26,
        "fijos": [("Renta", 9000), ("Asistente", 6000), ("Internet", 500), ("Contador", 800)],
        "variables": [
            ("Electricidad", 1500),
            ("Agua", 200),
            ("Servicio de limpieza", 600),
            ("Mantenimiento", 400),
        ],
        "equipo": 90000,
    },
    "extraccion": {
        "nombre": "Extracción",
        "consultorio": "DEMO Extracción",
        "usuario": "Usuario demo 4",
        "tratamiento": "Exodoncia Premolares",
        "especialidad": "Cirugía oral",
        "horas": 8,
        "dias": 4,
        "ocupacion": 60,
        "duracion": 30,
        "incremento": 225,
        "precio": "1050.00",
        "insumos": 17,
        "fijos": [("Renta", 8000), ("Asistente", 5500), ("Internet", 500), ("Contador", 700)],
        "variables": [
            ("Electricidad", 1800),
            ("Agua", 200),
            ("Servicio de limpieza", 700),
            ("Mantenimiento", 400),
        ],
        "equipo": 72000,
    },
    "ortodoncia": {
        "nombre": "Ortodoncia",
        "consultorio": "DEMO Ortodoncia",
        "usuario": "Usuario demo 5",
        "tratamiento": "Consulta mensual de ortodoncia convencional",
        "especialidad": "Ortodoncia",
        "horas": 8,
        "dias": 5,
        "ocupacion": 70,
        "duracion": 30,
        "incremento": 150,
        "precio": "1250.00",
        "insumos": 30,
        "fijos": [("Renta", 12000), ("Asistente", 6500), ("Internet", 500), ("Contador", 1000)],
        "variables": [
            ("Electricidad", 2000),
            ("Agua", 300),
            ("Servicio de limpieza", 800),
            ("Mantenimiento", 900),
        ],
        "equipo": 120000,
    },
}

COMMON: list[Material] = [
    ("Guantes", "caja", "PZA", 100, 4),
    ("Cubrebocas", "caja", "PZA", 58, 1),
    ("Bolsas para esterilizar", "paquete", "PZA", 300, 6),
    ("Punta de eyector", "bolsa", "PZA", 67.50, 2),
    ("Punta de jeringa triple", "paquete", "PZA", 392, 2),
    ("Aguja", "caja", "PZA", 229, 1),
    ("Cartucho de anestesia", "caja", "PZA", 744, 1),
    ("Campo operatorio", "bolsa", "PZA", 53, 3),
    ("Gasas", "bolsa", "PZA", 28.45, 6),
    ("Algodones", "bolsa", "PZA", 384, 2),
    ("Vaso desechable", "bote", "PZA", 337.93, 2),
    ("Servilletas", "paquete", "PZA", 40, 1),
    ("Enjuague", "botella", "ML", 146, 15),
    ("Hisopo", "bolsa", "PZA", 65, 2),
    ("Anestésico tópico", "frasco", "G", 146, Decimal("0.1")),
]
CONTENTS = {
    "Guantes": 100,
    "Cubrebocas": 50,
    "Bolsas para esterilizar": 300,
    "Punta de eyector": 100,
    "Punta de jeringa triple": 100,
    "Aguja": 100,
    "Cartucho de anestesia": 50,
    "Campo operatorio": 100,
    "Gasas": 100,
    "Algodones": 100,
    "Vaso desechable": 100,
    "Servilletas": 360,
    "Enjuague": 1000,
    "Hisopo": 300,
    "Anestésico tópico": 30,
    "Copa de hule": 1,
    "Cepillo profiláctico": 1,
    "Pasta profiláctica": 200,
    "Composite Esmalte": 1,
    "Composite Relleno": 15,
    "Ácido grabador": 30,
    "Primer": 5,
    "Clorhexidina": 1.5,
    "Disco soflex": 20,
    "Fresas": 1,
    "Microbrush": 100,
    "Dique": 50,
    "Papel de articular": 50,
    "Fresa de arkansas": 1,
    "Polyshine": 100,
    "Kit de pulido": 9,
    "Ionómero de vidrio base Ionosit": 1500,
    "Hilo de sutura catgut 3-0": 12,
    "Hoja de bisturí #15": 1,
    "Agua oxigenada": 230,
    "Fresa quirúrgica": 1,
    "Arcos niti térmicos": 10,
    "Arcos SS": 10,
    "Módulos": 40,
    "Elásticos": 100,
    "Resina de bracket": 4,
    "Adhesivo": 5,
    "Hooks crimpables": 10,
    "open coil (tramo de 1 cm)": 30,
    "e-links": 100,
    "cadena (tramo de 1 cm)": 230,
    "Bumper sleeve (tramo de 1 cm)": 500,
    "Ligadura metálica": 10,
    "Resina Fluida": 2,
}
EXTRAS: dict[str, list[Material]] = {
    "limpieza": [
        ("Copa de hule", "unidad", "PZA", 1.90, 1),
        ("Cepillo profiláctico", "unidad", "PZA", 2.10, 1),
        ("Pasta profiláctica", "frasco", "G", 106, 5),
    ],
    "resina": [
        ("Composite Esmalte", "tubo", "G", 714, 0.2),
        ("Composite Relleno", "tubo", "G", 500, 0.2),
        ("Ácido grabador", "jeringa", "ML", 1250, 0.1),
        ("Primer", "frasco", "ML", 1084, 0.03),
        ("Clorhexidina", "jeringa", "ML", 50.20, 0.25),
        ("Disco soflex", "bolsa", "PZA", 1638.40, 1),
        ("Fresas", "unidad", "PZA", 42, 1),
        ("Microbrush", "unidad", "PZA", 80, 4),
        ("Dique", "paquete", "PZA", 360, 1),
        ("Papel de articular", "paquete", "PZA", 174, 1),
        ("Fresa de arkansas", "unidad", "PZA", 55.30, 1),
        ("Polyshine", "tubo", "G", 285.50, 2),
        ("Kit de pulido", "unidad", "PZA", 335.12, 1),
        ("Ionómero de vidrio base Ionosit", "jeringa", "MG", 2205.75, 50),
    ],
    "extraccion": [
        ("Hilo de sutura catgut 3-0", "paquete", "PZA", 742, 1),
        ("Hoja de bisturí #15", "unidad", "PZA", 2.60, 1),
        ("Agua oxigenada", "botella", "ML", 24, 10),
        ("Fresa quirúrgica", "bolsa", "PZA", 38.48, 1),
    ],
    "ortodoncia": [
        ("Arcos niti térmicos", "paquete", "PZA", 119, 1),
        ("Arcos SS", "paquete", "PZA", 332, 1),
        ("Módulos", "paquete", "PZA", 450, 1),
        ("Elásticos", "bolsa", "PZA", 16, 100),
        ("Ácido grabador", "tubo", "ML", 1250, 0.5),
        ("Resina de bracket", "tubo", "G", 1500, 0.1),
        ("Microbrush", "unidad", "PZA", 80, 2),
        ("Adhesivo", "frasco", "ML", 1500, 0.05),
        ("Hooks crimpables", "pieza", "PZA", 213, 4),
        ("open coil (tramo de 1 cm)", "rollo", "CM", 190, 1),
        ("e-links", "bolsa", "PZA", 270.37, 4),
        ("cadena (tramo de 1 cm)", "rollo", "CM", 423, 3),
        ("Bumper sleeve (tramo de 1 cm)", "rollo", "CM", 272, 5),
        ("Ligadura metálica", "rollo", "G", 60, 0.1),
        ("Resina Fluida", "tubo", "G", 260, 0.25),
    ],
}


def _scenario_response(key: str) -> dict:
    s = SCENARIOS[key]
    return {
        "clave": key,
        "nombre": s["nombre"],
        "consultorio": s["consultorio"],
        "usuario": s["usuario"],
        "tratamiento": s["tratamiento"],
        "especialidad": s["especialidad"],
        "horas_por_dia": s["horas"],
        "dias_por_semana": s["dias"],
        "ocupacion": s["ocupacion"],
        "duracion_clinica": s["duracion"],
        "entre_citas": 10,
        "incremento_porcentaje": s["incremento"],
        "precio_sugerido": s["precio"],
        "insumos": s["insumos"],
    }


def _eliminar_demo_registrado(sesion: Session, organizacion: UUID, usuario: UUID) -> None:
    registro = sesion.execute(
        text(
            "SELECT identificador_usuario FROM sesion_demo_invitado "
            "WHERE identificador_organizacion=:o"
        ),
        {"o": organizacion},
    ).scalar_one_or_none()
    if registro is None or registro != usuario:
        raise ErrorAplicacion("SIN_PERMISO", "Solo se pueden eliminar organizaciones demo.", 403)

    otras_membresias = sesion.scalar(
        text(
            "SELECT count(*) FROM membresia_usuario_en_organizacion "
            "WHERE identificador_usuario=:u AND identificador_organizacion<>:o"
        ),
        {"u": usuario, "o": organizacion},
    )
    if otras_membresias:
        raise ErrorAplicacion(
            "SIN_PERMISO", "La cuenta demo tiene otra organización asociada.", 403
        )

    sesion.execute(
        text("SELECT eliminar_sesion_demo(:o, :u)"),
        {"o": organizacion, "u": usuario},
    )


def _limpiar_demos_vencidos(sesion: Session) -> None:
    vencidos = (
        sesion.execute(
            text(
                "SELECT DISTINCT identificador_organizacion,identificador_usuario "
                "FROM token_actualizacion_sesion "
                "WHERE es_invitado AND fecha_hora_expiracion_invitado <= now()"
            )
        )
        .mappings()
        .all()
    )
    for demo in vencidos:
        organizacion = demo["identificador_organizacion"]
        fijar_contexto_organizacion(sesion, organizacion)
        _eliminar_demo_registrado(sesion, organizacion, demo["identificador_usuario"])


@router.get("/escenarios", response_model=ListaEscenariosDemo)
def listar_escenarios() -> dict:
    return {"elementos": [_scenario_response(key) for key in SCENARIOS]}


@router.post(
    "/sesiones",
    status_code=status.HTTP_201_CREATED,
    response_model=SesionDemo,
)
def crear_sesion_demo(
    entrada: CrearDemoEntrada,
    request: Request,
    response: Response,
    sesion: Session = Depends(obtener_sesion),
) -> dict:
    limitar_intentos(f"demo:{request.client.host if request.client else 'desconocido'}")
    key = entrada.clave_escenario.lower()
    if key not in SCENARIOS:
        raise no_encontrado("El escenario demo solicitado no existe.")
    s = SCENARIOS[key]
    ahora = datetime.now(UTC)
    expira = ahora + timedelta(hours=24)
    with sesion.begin():
        _limpiar_demos_vencidos(sesion)
        correo = f"demo-{UUID(int=secrets.randbits(128))}@demo.medalyze.lat"
        usuario = sesion.scalar(
            text(
                "INSERT INTO usuario_plataforma (correo,hash_contrasena,nombre_completo) VALUES (:correo,:hash,:nombre) RETURNING identificador"
            ),
            {
                "correo": correo,
                "hash": hash_contrasena(secrets.token_urlsafe(24)),
                "nombre": s["usuario"],
            },
        )
        organizacion = sesion.scalar(
            text(
                "INSERT INTO organizacion_consultorio (nombre_comercial,espaciado_por_defecto) VALUES (:nombre,10) RETURNING identificador"
            ),
            {"nombre": s["consultorio"]},
        )
        fijar_contexto_organizacion(sesion, organizacion)
        sesion.execute(
            text(
                "INSERT INTO membresia_usuario_en_organizacion (identificador_usuario,identificador_organizacion) VALUES (:u,:o)"
            ),
            {"u": usuario, "o": organizacion},
        )
        sesion.execute(
            text(
                "INSERT INTO preferencias_onboarding_usuario (identificador_usuario,identificador_organizacion,ruta,situacion,ultimo_paso,completado,seleccion_parcial) VALUES (:u,:o,'CAPTURA_DIRECTA_DATOS','YA_ATIENDE_EN_CONSULTA_PRIVADA','clinico',true,:seleccion)"
            ),
            {"u": usuario, "o": organizacion, "seleccion": '{"escenario":"' + key + '"}'},
        )
        sesion.execute(
            text(
                "INSERT INTO sesion_demo_invitado (identificador_usuario,identificador_organizacion,clave_escenario,expira_en) VALUES (:u,:o,:key,:expira)"
            ),
            {"u": usuario, "o": organizacion, "key": key, "expira": expira},
        )
        sesion.execute(
            text(
                "INSERT INTO perfil_capacidad_atencion (identificador_organizacion,dias_por_semana,horas_por_dia,porcentaje_ocupacion,ocupacion_confirmada) VALUES (:o,:dias,:horas,:ocupacion,true)"
            ),
            {
                "o": organizacion,
                "dias": s["dias"],
                "horas": s["horas"],
                "ocupacion": s["ocupacion"],
            },
        )
        for categoria, gastos in (("FIJO", s["fijos"]), ("VARIABLE", s["variables"])):
            for nombre, importe in gastos:
                sesion.execute(
                    text(
                        "INSERT INTO gasto_registrado (identificador_organizacion,nombre,categoria,importe_pagado_por_periodo,codigo_periodicidad,fecha_inicio_vigencia) VALUES (:o,:nombre,:categoria,:importe,'MENSUAL','2026-01-01')"
                    ),
                    {
                        "o": organizacion,
                        "nombre": nombre,
                        "categoria": categoria,
                        "importe": importe,
                    },
                )
        sesion.execute(
            text(
                "INSERT INTO equipo_o_instalacion_depreciable (identificador_organizacion,nombre,precio_adquisicion,valor_residual,vida_util_anios,fecha_alta_en_servicio) VALUES (:o,'Unidad dental',:precio,0,5,'2026-01-01')"
            ),
            {"o": organizacion, "precio": s["equipo"]},
        )
        insumos = (
            COMMON[:12] if key == "resina" else COMMON[:13] if key == "extraccion" else COMMON
        ) + EXTRAS.get(key, [])
        ids = []
        for nombre, presentacion, unidad, precio, cantidad in insumos:
            contenido = CONTENTS[nombre]
            ident = sesion.scalar(
                text(
                    "INSERT INTO insumo_clinico (identificador_organizacion,nombre,presentacion,codigo_unidad,cantidad_contenida) VALUES (:o,:nombre,:presentacion,:unidad,:contenido) RETURNING identificador"
                ),
                {
                    "o": organizacion,
                    "nombre": nombre,
                    "presentacion": presentacion,
                    "unidad": unidad,
                    "contenido": contenido,
                },
            )
            ids.append((ident, cantidad))
            sesion.execute(
                text(
                    "INSERT INTO precio_historico_insumo (identificador_insumo,precio_presentacion,cantidad_contenida) VALUES (:id,:precio,:contenido)"
                ),
                {"id": ident, "precio": precio, "contenido": contenido},
            )
        tratamiento = sesion.scalar(
            text(
                "INSERT INTO tratamiento (identificador_organizacion,nombre,especialidad) VALUES (:o,:nombre,:especialidad) RETURNING identificador"
            ),
            {"o": organizacion, "nombre": s["tratamiento"], "especialidad": s["especialidad"]},
        )
        sesion.execute(
            text(
                "UPDATE preferencias_onboarding_usuario SET seleccion_parcial=:seleccion WHERE identificador_usuario=:u"
            ),
            {
                "u": usuario,
                "seleccion": '{"escenario":"'
                + key
                + '","tratamiento_id":"'
                + str(tratamiento)
                + '","paso":"clinico"}',
            },
        )
        version = sesion.scalar(
            text(
                "INSERT INTO version_configuracion_tratamiento (identificador_tratamiento,numero_version,nombre,especialidad,duracion_clinica,espaciado,metodo,ajuste_porcentaje) VALUES (:t,1,:nombre,:especialidad,:duracion,NULL,'RECETA_INSUMOS',:ajuste) RETURNING identificador"
            ),
            {
                "t": tratamiento,
                "nombre": s["tratamiento"],
                "especialidad": s["especialidad"],
                "duracion": s["duracion"],
                "ajuste": s["incremento"],
            },
        )
        for ident, cantidad in ids:
            sesion.execute(
                text(
                    "INSERT INTO linea_receta_insumos_tratamiento (identificador_version_configuracion,identificador_insumo,cantidad) VALUES (:v,:i,:cantidad)"
                ),
                {"v": version, "i": ident, "cantidad": cantidad},
            )
        sesion.execute(
            text("UPDATE tratamiento SET identificador_version_vigente=:v WHERE identificador=:t"),
            {"v": version, "t": tratamiento},
        )
        acceso, refresh, segundos = _crear_sesion(
            sesion, usuario, organizacion, "PROPIETARIO", True, expira
        )
        fila = {
            "usuario_id": usuario,
            "nombre_completo": s["usuario"],
            "correo": correo,
            "rol": "PROPIETARIO",
            "organizacion_id": organizacion,
            "nombre_comercial": s["consultorio"],
            "codigo_moneda": "MXN",
            "multiplo_redondeo": 50,
            "espaciado_por_defecto": 10,
            "organizacion_revision": 0,
            "onboarding_completado": True,
            "modo_invitado": True,
            "escenario": _scenario_response(key),
            "expira_en": expira.isoformat(),
        }
    _establecer_cookie(response, refresh, 24 * 60 * 60)
    return _respuesta_sesion(
        fila,
        acceso,
        segundos,
        {"version_aceptada": None, "aceptado_en": None, "requiere_aceptar": False},
    )


@router.delete(
    "/sesiones/actual",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    openapi_extra={"security": [{"BearerJWT": []}]},
)
def eliminar_sesion_demo(
    contexto: ContextoSolicitud = Depends(obtener_contexto),
    sesion: Session = Depends(obtener_sesion_protegida, scope="function"),
) -> Response:
    _eliminar_demo_registrado(sesion, contexto.organizacion, contexto.usuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
