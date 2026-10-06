"""Regresiones de la revisión del PR de BE-01..BE-10, contra PostgreSQL 16 real.

Cada prueba reproduce un fallo comprobado antes de corregirlo. Se activan igual que las demás
pruebas de PostgreSQL: MEDALYZE_TEST_POSTGRES=1 con las migraciones aplicadas.
"""

import os
import threading
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def admin():
    if os.getenv("MEDALYZE_TEST_POSTGRES") != "1":
        pytest.skip("Las pruebas PostgreSQL se ejecutan con MEDALYZE_TEST_POSTGRES=1.")
    motor = create_engine(os.environ["ALEMBIC_DATABASE_URL"], pool_pre_ping=True)
    yield motor
    motor.dispose()


@pytest.fixture(scope="module")
def cliente(admin):
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def consultorio(cliente):
    correo = f"regresion-{uuid.uuid4().hex[:10]}@ejemplo.mx"
    r = cliente.post(
        "/api/v1/autenticacion/registro",
        json={
            "nombre_completo": "Dra. Regresión",
            "correo": correo,
            "contrasena": "una-contrasena-larga-1",
            "nombre_consultorio": "Consultorio de regresión",
        },
    )
    assert r.status_code == 201
    cuerpo = r.json()
    return {
        "org": cuerpo["organizacion"]["identificador"],
        "encabezado": {"Authorization": f"Bearer {cuerpo['token_acceso']}"},
        "refresh": cuerpo["token_actualizacion"],
    }


def _sembrar_tratamiento(admin, org: str, **config) -> str:
    tratamiento, version = str(uuid.uuid4()), str(uuid.uuid4())
    with admin.begin() as c:
        c.execute(text("""INSERT INTO perfil_capacidad_atencion
            (identificador_organizacion,dias_por_semana,horas_por_dia,porcentaje_ocupacion)
            VALUES (:o,5,8,75)"""), {"o": org})
        c.execute(text("INSERT INTO tratamiento (identificador,identificador_organizacion,nombre,especialidad) VALUES (:t,:o,'Profilaxis','GENERAL')"), {"t": tratamiento, "o": org})
        c.execute(text("""INSERT INTO version_configuracion_tratamiento
            (identificador,identificador_tratamiento,numero_version,nombre,especialidad,duracion_clinica,espaciado,metodo,importe_materiales,ajuste_porcentaje)
            VALUES (:v,:t,1,'Profilaxis','GENERAL',30,10,'IMPORTE_RAPIDO',:mat,:ajuste)"""),
            {"v": version, "t": tratamiento, "mat": config.get("materiales", 60), "ajuste": config.get("ajuste", 50)})
        c.execute(text("UPDATE tratamiento SET identificador_version_vigente=:v WHERE identificador=:t"), {"v": version, "t": tratamiento})
    return tratamiento


def _gasto(admin, org: str, importe: int, periodicidad: str) -> None:
    with admin.begin() as c:
        c.execute(text("""INSERT INTO gasto_registrado
            (identificador_organizacion,nombre,categoria,importe_pagado_por_periodo,codigo_periodicidad,fecha_inicio_vigencia)
            VALUES (:o,'Gasto','FIJO',:i,:p,'2026-01-01')"""), {"o": org, "i": importe, "p": periodicidad})


# ---------------------------------------------------------------- pantallas principales

def test_lista_de_tratamientos_responde_con_y_sin_filtros(cliente, consultorio) -> None:
    for consulta in ("", "?archivados=true", "?estado=", "?estado=CALCULADO", "?busqueda=limpieza"):
        r = cliente.get(f"/api/v1/tratamientos{consulta}", headers=consultorio["encabezado"])
        assert r.status_code == 200, consulta


def test_catalogo_de_plantillas_responde_con_y_sin_filtros(cliente, consultorio) -> None:
    for consulta in ("", "?mis_areas=true", "?mis_areas=false", "?especialidad=GENERAL"):
        r = cliente.get(f"/api/v1/plantillas-tratamiento{consulta}", headers=consultorio["encabezado"])
        assert r.status_code == 200, consulta
    assert len(r.json()["elementos"]) > 0


# ---------------------------------------------------------------- archivar / restaurar

def test_archivar_y_restaurar_un_tratamiento(cliente, admin, consultorio) -> None:
    t = _sembrar_tratamiento(admin, consultorio["org"])
    archivar = cliente.post(f"/api/v1/tratamientos/{t}/archivar", headers={**consultorio["encabezado"], "If-Match": "0"})
    assert archivar.status_code == 200
    assert archivar.json()["estado"] == "ARCHIVADO"
    restaurar = cliente.post(f"/api/v1/tratamientos/{t}/restaurar", headers={**consultorio["encabezado"], "If-Match": "1"})
    assert restaurar.status_code == 200
    assert restaurar.json()["estado"] == "BORRADOR"  # sin hoja de costos todavía


def test_restaurar_no_presenta_como_vigente_un_precio_que_pudo_quedar_viejo(cliente, admin, consultorio) -> None:
    org, h = consultorio["org"], consultorio["encabezado"]
    _gasto(admin, org, 7800, "MENSUAL")
    t = _sembrar_tratamiento(admin, org)
    r = cliente.post(f"/api/v1/tratamientos/{t}/calculos", json={"revision_tratamiento": 0},
                     headers={**h, "If-Match": "0", "Idempotency-Key": f"clave-{uuid.uuid4().hex}"})
    assert r.status_code == 201
    assert cliente.post(f"/api/v1/tratamientos/{t}/archivar", headers={**h, "If-Match": "1"}).status_code == 200
    restaurado = cliente.post(f"/api/v1/tratamientos/{t}/restaurar", headers={**h, "If-Match": "2"})
    assert restaurado.json()["estado"] == "CAMBIOS_POR_REVISAR"


# ---------------------------------------------------------------- sesión

def test_reutilizar_un_refresh_token_revoca_toda_la_familia(cliente, consultorio) -> None:
    primero = consultorio["refresh"]
    r = cliente.post("/api/v1/autenticacion/renovacion", json={"token_actualizacion": primero})
    assert r.status_code == 200
    segundo = r.json()["token_actualizacion"]
    robo = cliente.post("/api/v1/autenticacion/renovacion", json={"token_actualizacion": primero})
    assert robo.status_code == 401
    # Antes de la corrección este token seguía vivo: la revocación se perdía en el rollback.
    legitimo = cliente.post("/api/v1/autenticacion/renovacion", json={"token_actualizacion": segundo})
    assert legitimo.status_code == 401


# ---------------------------------------------------------------- idempotencia

def test_clave_reservada_por_otra_solicitud_en_curso_repite_su_respuesta(cliente, admin, consultorio) -> None:
    """Fuerza la carrera del doble clic de forma determinista.

    Otra solicitud ya reservó la clave y todavía no confirma. La API debe esperar y, al confirmar la
    otra, devolver SU respuesta. Antes: UniqueViolation -> HTTP 500.
    """
    import time

    import jwt

    from app.infrastructure.idempotencia import hash_cuerpo

    org, h = consultorio["org"], consultorio["encabezado"]
    _gasto(admin, org, 7800, "MENSUAL")
    t = _sembrar_tratamiento(admin, org)
    usuario = jwt.decode(h["Authorization"].split()[1], options={"verify_signature": False})["sub"]
    clave, operacion = f"carrera-{uuid.uuid4().hex}", f"calcular:{t}"
    llaves = {"o": org, "u": usuario, "op": operacion, "c": clave}

    otra = admin.connect()
    transaccion = otra.begin()
    otra.execute(text("""INSERT INTO solicitud_idempotente
        (identificador_organizacion,identificador_usuario,operacion,clave,hash_cuerpo)
        VALUES (:o,:u,:op,:c,:h)"""), {**llaves, "h": hash_cuerpo({"revision_tratamiento": 0})})
    resultado: dict = {}

    def llamar() -> None:
        resultado["r"] = cliente.post(
            f"/api/v1/tratamientos/{t}/calculos", json={"revision_tratamiento": 0},
            headers={**h, "If-Match": "0", "Idempotency-Key": clave})

    hilo = threading.Thread(target=llamar)
    hilo.start()
    time.sleep(1.5)  # la API ya está esperando la reserva de la otra solicitud
    otra.execute(text("""UPDATE solicitud_idempotente SET estado_http=201, respuesta='{"ya":"calculada"}'::jsonb
        WHERE identificador_organizacion=:o AND identificador_usuario=:u AND operacion=:op AND clave=:c"""), llaves)
    transaccion.commit()
    otra.close()
    hilo.join(15)
    assert resultado["r"].status_code == 201
    assert resultado["r"].json() == {"ya": "calculada"}
    with admin.begin() as c:
        hojas = c.scalar(text("SELECT count(*) FROM hoja_costos_tratamiento WHERE identificador_tratamiento=:t"), {"t": t})
    assert hojas == 0  # la solicitud que esperaba no duplicó el cálculo


# ---------------------------------------------------------------- exactitud financiera

def test_gasto_semestral_exacto_no_sube_el_precio_un_multiplo(cliente, admin, consultorio) -> None:
    """46,800 semestral = 7,800/mes exactos => costo ajustado 150 => precio 150 (antes: 200)."""
    org, h = consultorio["org"], consultorio["encabezado"]
    _gasto(admin, org, 46800, "SEMESTRAL")
    t = _sembrar_tratamiento(admin, org, materiales=60, ajuste=50)
    r = cliente.post(f"/api/v1/tratamientos/{t}/calculos", json={"revision_tratamiento": 0},
                     headers={**h, "If-Match": "0", "Idempotency-Key": f"clave-{uuid.uuid4().hex}"})
    assert r.status_code == 201
    assert Decimal(r.json()["precio_sugerido"]) == Decimal("150")
    assert Decimal(r.json()["pool_mensual"]) == Decimal("7800")


def test_un_equipo_con_vida_util_agotada_no_suma_depreciacion(cliente, admin, consultorio) -> None:
    org, h = consultorio["org"], consultorio["encabezado"]
    hoy = date.today()
    with admin.begin() as c:
        c.execute(text("""INSERT INTO equipo_o_instalacion_depreciable
            (identificador_organizacion,nombre,precio_adquisicion,valor_residual,vida_util_anios,fecha_alta_en_servicio)
            VALUES (:o,'Sillón antiguo',36000,0,3,:antiguo), (:o,'Sillón vigente',36000,0,3,:reciente)"""),
            {"o": org, "antiguo": date(hoy.year - 6, 1, 1), "reciente": date(hoy.year - 1, 1, 1)})
    r = cliente.get("/api/v1/costos-indirectos/resumen", headers=h)
    assert r.status_code == 200
    assert Decimal(str(r.json()["depreciacion"])) == Decimal("1000")  # solo el vigente (36,000 / 36 meses)


# ---------------------------------------------------------------- historial inmutable y validación

def test_el_historial_de_precios_no_se_puede_borrar_directamente(admin, consultorio) -> None:
    from app.core.database import fabrica_sesiones, fijar_contexto_organizacion
    org = uuid.UUID(consultorio["org"])
    insumo = uuid.uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO insumo_clinico (identificador,identificador_organizacion,nombre,codigo_unidad,cantidad_contenida) VALUES (:i,:o,'Guantes','PZA',100)"), {"i": insumo, "o": org})
        c.execute(text("INSERT INTO precio_historico_insumo (identificador_insumo,precio_presentacion,cantidad_contenida) VALUES (:i,180,100)"), {"i": insumo})
    with fabrica_sesiones() as s:
        s.begin()
        fijar_contexto_organizacion(s, org)
        with pytest.raises(Exception, match="inmutable"):
            s.execute(text("DELETE FROM precio_historico_insumo WHERE identificador_insumo=:i"), {"i": insumo})
        s.rollback()
    # ...pero eliminar el insumo (sin uso) sí arrastra su historial por cascada
    with fabrica_sesiones() as s:
        s.begin()
        fijar_contexto_organizacion(s, org)
        s.execute(text("DELETE FROM insumo_clinico WHERE identificador=:i"), {"i": insumo})
        s.commit()


def test_un_codigo_de_periodicidad_inexistente_es_un_error_422_no_un_500(cliente, consultorio) -> None:
    r = cliente.post("/api/v1/gastos", headers=consultorio["encabezado"], json={
        "nombre": "Seguro", "categoria": "FIJO", "importe_pagado_por_periodo": "100",
        "codigo_periodicidad": "DECENAL", "fecha_inicio_vigencia": "2026-01-01"})
    assert r.status_code == 422


def test_una_especialidad_inexistente_es_un_error_422_no_un_500(cliente, consultorio) -> None:
    r = cliente.patch("/api/v1/perfil", headers={**consultorio["encabezado"], "If-Match": "0"},
                      json={"nombre_para_mostrar": "Dra. X", "especialidades": [str(uuid.uuid4())]})
    assert r.status_code == 422


# ---------------------------------------------------------------- entradas inválidas: 422, nunca 500

@pytest.mark.parametrize("residual", ["100", "150"])
def test_equipo_con_valor_residual_no_menor_al_precio_es_422(cliente, consultorio, residual: str) -> None:
    r = cliente.post("/api/v1/equipos", headers=consultorio["encabezado"], json={
        "nombre": "Sillón", "precio_adquisicion": "100", "valor_residual": residual, "vida_util_anios": 5})
    assert r.status_code == 422


def test_equipo_valido_se_crea(cliente, consultorio) -> None:
    r = cliente.post("/api/v1/equipos", headers=consultorio["encabezado"], json={
        "nombre": "Sillón", "precio_adquisicion": "12000", "valor_residual": "1200", "vida_util_anios": 3})
    assert r.status_code == 201


@pytest.mark.parametrize("horas", ["0", "0.001", "5e-324", "25"])
def test_horas_de_atencion_fuera_de_rango_son_422(cliente, consultorio, horas: str) -> None:
    r = cliente.put("/api/v1/perfil-capacidad", headers={**consultorio["encabezado"], "If-Match": "0"}, json={
        "dias_por_semana": 5, "horas_por_dia": horas, "porcentaje_ocupacion": 70})
    assert r.status_code == 422


@pytest.mark.parametrize("if_match", ["", "abc", "1.5"])
def test_calculo_con_if_match_invalido_no_produce_500(cliente, admin, consultorio, if_match: str) -> None:
    t = _sembrar_tratamiento(admin, consultorio["org"])
    r = cliente.post(f"/api/v1/tratamientos/{t}/calculos", json={"revision_tratamiento": 0},
                     headers={**consultorio["encabezado"], "If-Match": if_match,
                              "Idempotency-Key": f"clave-{uuid.uuid4().hex}"})
    assert r.status_code in (422, 428)
