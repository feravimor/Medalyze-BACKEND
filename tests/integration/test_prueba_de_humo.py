"""Prueba de humo de toda la API contra PostgreSQL real.

Recorre la aplicación como lo haría un odontólogo: crea su cuenta, configura su consultorio,
captura costos, equipos, insumos y datos mensuales, crea tratamientos con los tres métodos de
materiales, calcula precios y consulta el historial. Está pensada para ejercitar **las 56
operaciones del contrato** y, de paso, servir de guion para la demostración.

Qué verifica:
  * cada operación del contrato responde con éxito al menos una vez (cobertura 56/56);
  * cada respuesta, de éxito o de error, cumple el esquema documentado en ``openapi.yaml``;
  * los casos de error esperables (sin sesión, otro consultorio, revisión vieja, datos inválidos)
    devuelven 401, 404, 409, 428 o 422, y nunca 500;
  * los resultados del motor coinciden con los números del manual.

Los pasos se ejecutan en el orden en que están escritos y comparten estado (``ESTADO``): si un paso
previo falla, los que dependen de él se omiten con un mensaje claro.

Requiere ``MEDALYZE_TEST_POSTGRES=1`` y las migraciones aplicadas, como el resto de las pruebas
de PostgreSQL.
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from humo_base import Api, Contrato, buscar, clave_nueva

pytestmark = pytest.mark.postgres

CONTRASENA = "una-contrasena-larga-1"
CONTRATO = Contrato()
ESTADO: dict[str, Any] = {}
HOY = date.today()
MES_0 = HOY.replace(day=1)
MES_1 = (MES_0 - timedelta(days=1)).replace(day=1)
MES_2 = (MES_1 - timedelta(days=1)).replace(day=1)


def E(clave: str) -> Any:
    """Dato que dejó un paso anterior; si no existe, se omite el paso con un aviso claro."""
    if clave not in ESTADO:
        pytest.skip(f"Falta el paso previo que crea «{clave}».")
    return ESTADO[clave]


def d(valor: Any) -> Decimal:
    return Decimal(str(valor))


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    if os.getenv("MEDALYZE_TEST_POSTGRES") != "1":
        pytest.skip("Las pruebas PostgreSQL se ejecutan con MEDALYZE_TEST_POSTGRES=1.")
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def _registrar(cliente: TestClient, nombre: str) -> Api:
    api = Api(cliente, CONTRATO)
    correo = f"humo-{os.urandom(5).hex()}@ejemplo.mx"
    r = api(
        "POST",
        "/autenticacion/registro",
        json={
            "nombre_completo": nombre,
            "correo": correo,
            "contrasena": CONTRASENA,
            "nombre_consultorio": f"Consultorio de {nombre}",
        },
        sesion=False,
        estado=201,
    )
    cuerpo = r.json()
    api.token = cuerpo["token_acceso"]
    api.correo = correo  # type: ignore[attr-defined]
    api.org = cuerpo["organizacion"]["identificador"]  # type: ignore[attr-defined]
    api.refresh = cuerpo["token_actualizacion"]  # type: ignore[attr-defined]
    return api


@pytest.fixture(scope="module")
def A(cliente: TestClient) -> Api:
    return _registrar(cliente, "Dra. Humo")


@pytest.fixture(scope="module")
def B(cliente: TestClient) -> Api:
    return _registrar(cliente, "Dr. Otro")


def comprobar_concurrencia(api: Api, metodo: str, ruta: str, cuerpo: Any, revision: int) -> None:
    """Sin If-Match debe responder 428; con una revisión vieja, 409 CONFLICTO_REVISION."""
    r = api(metodo, ruta, json=cuerpo)
    assert r.status_code == 428, f"{metodo} {ruta} sin If-Match: {r.status_code} {r.text[:200]}"
    assert r.json()["detalle"]["codigo"] == "REVISION_REQUERIDA"
    r = api(metodo, ruta, json=cuerpo, rev=revision + 1000)
    assert r.status_code == 409, f"{metodo} {ruta} con revisión vieja: {r.status_code} {r.text[:200]}"
    assert r.json()["detalle"]["codigo"] == "CONFLICTO_REVISION"


# --------------------------------------------------------------------------- 1 · salud


def test_salud_responde_sin_sesion(cliente: TestClient) -> None:
    api = Api(cliente, CONTRATO)
    api("GET", "/health", sesion=False, estado=200)
    api("GET", "/ready", sesion=False, estado=200)


# --------------------------------------------------------------------------- 2 · autenticación


def test_el_registro_crea_cuenta_consultorio_y_onboarding(A: Api) -> None:
    r = A("GET", "/autenticacion/usuario-actual", estado=200)
    assert r.json()["usuario"]["correo"] == A.correo  # type: ignore[attr-defined]
    ESTADO["org"] = A.org  # type: ignore[attr-defined]


def test_registro_con_correo_repetido_es_409_y_con_datos_invalidos_422(A: Api) -> None:
    r = A(
        "POST",
        "/autenticacion/registro",
        json={"nombre_completo": "Otra", "correo": A.correo, "contrasena": CONTRASENA},  # type: ignore[attr-defined]
        sesion=False,
    )
    assert r.status_code == 409, r.text[:200]
    r = A(
        "POST",
        "/autenticacion/registro",
        json={"nombre_completo": "X", "correo": "no-es-correo", "contrasena": "corta"},
        sesion=False,
    )
    assert r.status_code == 422


def test_inicio_de_sesion_renovacion_y_cierre(A: Api) -> None:
    r = A(
        "POST",
        "/autenticacion/inicio-sesion",
        json={"correo": A.correo, "contrasena": CONTRASENA},  # type: ignore[attr-defined]
        sesion=False,
        estado=200,
    )
    refresco = r.json()["token_actualizacion"]
    assert A(
        "POST",
        "/autenticacion/inicio-sesion",
        json={"correo": A.correo, "contrasena": "contrasena-equivocada"},  # type: ignore[attr-defined]
        sesion=False,
    ).status_code == 401
    r = A("POST", "/autenticacion/renovacion", json={"token_actualizacion": refresco}, sesion=False, estado=200)
    nuevo = r.json()["token_actualizacion"]
    assert nuevo != refresco
    A("POST", "/autenticacion/cierre-sesion", json={"token_actualizacion": nuevo}, estado=204)
    # El token cerrado ya no sirve para renovar.
    assert A("POST", "/autenticacion/renovacion", json={"token_actualizacion": nuevo}, sesion=False).status_code == 401


def test_cerrar_sesion_sin_enviar_el_token_de_renovacion_tambien_lo_revoca(A: Api) -> None:
    """El frontend llama al cierre de sesión sin cuerpo: antes devolvía 204 sin revocar y el token seguía vigente."""
    r = A("POST", "/autenticacion/inicio-sesion", json={"correo": A.correo, "contrasena": CONTRASENA}, sesion=False, estado=200).json()  # type: ignore[attr-defined]
    sesion_nueva = Api(A.cliente, CONTRATO, r["token_acceso"])
    sesion_nueva("POST", "/autenticacion/cierre-sesion", estado=204)
    despues = A("POST", "/autenticacion/renovacion", json={"token_actualizacion": r["token_actualizacion"]}, sesion=False)
    assert despues.status_code == 401, f"el token de renovación siguió funcionando tras cerrar sesión ({despues.status_code})"


def test_los_mensajes_de_validacion_llegan_en_espanol(A: Api) -> None:
    r = A("POST", "/autenticacion/registro", json={"nombre_completo": "", "correo": "no-es-correo", "contrasena": "corta"}, sesion=False)
    assert r.status_code == 422
    mensajes = {c["campo"]: c["mensaje"] for c in r.json()["detalle"]["campos"]}
    assert mensajes["contrasena"] == "Debe tener al menos 10 caracteres."
    assert mensajes["correo"] == "Escribe un correo electrónico válido."
    assert mensajes["nombre_completo"] == "No puede estar vacío."


# --------------------------------------------------------------------------- 3 · cuenta y onboarding


def test_catalogo_de_especialidades(A: Api) -> None:
    r = A("GET", "/especialidades", estado=200)
    elementos = r.json()["elementos"]
    assert len(elementos) == 10
    ESTADO["especialidades"] = [e["identificador"] for e in elementos]


def test_perfil_se_consulta_y_se_actualiza(A: Api) -> None:
    perfil = A("GET", "/perfil", estado=200).json()
    especialidades = E("especialidades")
    r = A(
        "PATCH",
        "/perfil",
        json={"nombre_para_mostrar": "Dra. Humo Pérez", "especialidades": especialidades[:2]},
        rev=perfil["revision"],
        estado=200,
    )
    nuevo = r.json()
    assert nuevo["nombre_para_mostrar"] == "Dra. Humo Pérez"
    assert sorted(nuevo["especialidades"]) == sorted(especialidades[:2])
    assert nuevo["revision"] == perfil["revision"] + 1
    comprobar_concurrencia(A, "PATCH", "/perfil", {"nombre_para_mostrar": "X"}, nuevo["revision"])


def test_perfil_con_especialidades_repetidas_o_inexistentes_no_es_un_500(A: Api) -> None:
    perfil = A("GET", "/perfil", estado=200).json()
    e0 = E("especialidades")[0]
    repetidas = A("PATCH", "/perfil", json={"especialidades": [e0, e0]}, rev=perfil["revision"])
    assert repetidas.status_code in (200, 422), f"especialidades repetidas → {repetidas.status_code} {repetidas.text[:160]}"
    perfil = A("GET", "/perfil", estado=200).json()
    inexistente = A(
        "PATCH",
        "/perfil",
        json={"especialidades": ["00000000-0000-4000-8000-000000000000"]},
        rev=perfil["revision"],
    )
    assert inexistente.status_code == 422, f"especialidad inexistente → {inexistente.status_code} {inexistente.text[:160]}"


def test_organizacion_se_consulta_y_se_actualiza(A: Api) -> None:
    org = A("GET", "/organizacion", estado=200).json()
    r = A(
        "PATCH",
        "/organizacion",
        json={"nombre_comercial": "Consultorio Humo", "multiplo_redondeo": "50", "espaciado_por_defecto": 10},
        rev=org["revision"],
        estado=200,
    )
    assert r.json()["espaciado_por_defecto"] == 10
    assert d(r.json()["multiplo_redondeo"]) == 50
    comprobar_concurrencia(A, "PATCH", "/organizacion", {"nombre_comercial": "X"}, r.json()["revision"])
    assert A("PATCH", "/organizacion", json={"espaciado_por_defecto": 99}, rev=r.json()["revision"]).status_code == 422


def test_onboarding_se_consulta_y_se_completa(A: Api) -> None:
    ob = A("GET", "/onboarding", estado=200).json()
    r = A(
        "PATCH",
        "/onboarding",
        json={
            "ruta": "ASISTENTE_GUIADO",
            "situacion": "YA_ATIENDE_EN_CONSULTA_PRIVADA",
            "ultimo_paso": "tratamientos",
            "seleccion_parcial": {"plantillas": ["general.profilaxis_dental"]},
            "completado": True,
        },
        rev=ob["revision"],
        estado=200,
    )
    assert r.json()["completado"] is True
    comprobar_concurrencia(A, "PATCH", "/onboarding", {"completado": True}, r.json()["revision"])


# --------------------------------------------------------------------------- 4 · capacidad


def test_capacidad_no_existe_hasta_que_se_captura(A: Api) -> None:
    assert A("GET", "/perfil-capacidad").status_code == 404


def test_capacidad_se_guarda_y_se_consulta(A: Api) -> None:
    cuerpo = {"dias_por_semana": 5, "horas_por_dia": "8", "porcentaje_ocupacion": "75", "ocupacion_confirmada": True}
    r = A("PUT", "/perfil-capacidad", json=cuerpo, rev=0, estado=200)
    assert r.json()["dias_por_semana"] == 5
    ESTADO["capacidad_revision"] = r.json()["revision"]
    leido = A("GET", "/perfil-capacidad", estado=200).json()
    assert d(leido["horas_por_dia"]) == 8 and d(leido["porcentaje_ocupacion"]) == 75


def test_capacidad_rechaza_valores_fuera_de_rango(A: Api) -> None:
    revision = E("capacidad_revision")
    malos = [
        {"dias_por_semana": 0, "horas_por_dia": "8", "porcentaje_ocupacion": "75"},
        {"dias_por_semana": 8, "horas_por_dia": "8", "porcentaje_ocupacion": "75"},
        {"dias_por_semana": 5, "horas_por_dia": "25", "porcentaje_ocupacion": "75"},
        {"dias_por_semana": 5, "horas_por_dia": "8", "porcentaje_ocupacion": "101"},
    ]
    for cuerpo in malos:
        assert A("PUT", "/perfil-capacidad", json=cuerpo, rev=revision).status_code == 422, cuerpo


def test_capacidad_detecta_ediciones_simultaneas(A: Api) -> None:
    """Dos personas cargan el mismo perfil; la segunda en guardar debe recibir 409, no pisar a la primera."""
    cuerpo = {"dias_por_semana": 5, "horas_por_dia": "8", "porcentaje_ocupacion": "75", "ocupacion_confirmada": True}
    cargado = A("GET", "/perfil-capacidad", estado=200).json()["revision"]
    A("PUT", "/perfil-capacidad", json=cuerpo, rev=cargado, estado=200)  # guarda la primera persona
    segunda = A("PUT", "/perfil-capacidad", json=cuerpo, rev=cargado)  # la segunda aún tiene la revisión vieja
    assert segunda.status_code == 409, (
        f"la segunda edición con una revisión vieja devolvió {segunda.status_code}: se perdió la edición anterior"
    )
    ESTADO["capacidad_revision"] = A("GET", "/perfil-capacidad", estado=200).json()["revision"]


# --------------------------------------------------------------------------- 5 · gastos


def _gasto(nombre: str, categoria: str, importe: str, periodicidad: str = "MENSUAL") -> dict[str, Any]:
    return {
        "nombre": nombre,
        "categoria": categoria,
        "importe_pagado_por_periodo": importe,
        "codigo_periodicidad": periodicidad,
        "fecha_inicio_vigencia": str(MES_2),
        "activo": True,
    }


def test_catalogo_de_periodicidades(A: Api) -> None:
    r = A("GET", "/periodicidades-pago", estado=200)
    assert {p["codigo"] for p in r.json()["elementos"]} == {
        "SEMANAL", "QUINCENAL", "MENSUAL", "BIMESTRAL", "TRIMESTRAL", "SEMESTRAL", "ANUAL",
    }


def test_gastos_se_crean_y_se_listan(A: Api) -> None:
    fijo = A("POST", "/gastos", json=_gasto("Renta", "FIJO", "6200"), estado=201).json()
    variable = A("POST", "/gastos", json=_gasto("Servicios", "VARIABLE", "1300"), estado=201).json()
    ESTADO["gasto_fijo"], ESTADO["gasto_variable"] = fijo, variable
    elementos = A("GET", "/gastos", estado=200).json()["elementos"]
    assert {g["nombre"] for g in elementos} >= {"Renta", "Servicios"}
    anual = A("POST", "/gastos", json=_gasto("Seguro", "FIJO", "2400", "ANUAL"), estado=201).json()
    en_lista = next(g for g in A("GET", "/gastos").json()["elementos"] if g["identificador"] == anual["identificador"])
    assert d(en_lista["equivalente_mensual"]) == 200  # 2,400 al año = 200 al mes, exacto
    A("DELETE", f"/gastos/{anual['identificador']}", rev=anual["revision"], estado=204)


def test_gasto_se_actualiza_y_detecta_ediciones_simultaneas(A: Api) -> None:
    fijo = E("gasto_fijo")
    r = A("PATCH", f"/gastos/{fijo['identificador']}", json=_gasto("Renta", "FIJO", "6200"), rev=fijo["revision"], estado=200)
    assert r.json()["revision"] == fijo["revision"] + 1
    ESTADO["gasto_fijo"] = r.json()
    comprobar_concurrencia(A, "PATCH", f"/gastos/{fijo['identificador']}", _gasto("Renta", "FIJO", "6200"), r.json()["revision"])


def test_gasto_se_elimina_una_sola_vez(A: Api) -> None:
    g = A("POST", "/gastos", json=_gasto("Temporal", "VARIABLE", "10"), estado=201).json()
    comprobar_concurrencia(A, "DELETE", f"/gastos/{g['identificador']}", None, g["revision"])
    A("DELETE", f"/gastos/{g['identificador']}", rev=g["revision"], estado=204)
    assert A("DELETE", f"/gastos/{g['identificador']}", rev=g["revision"]).status_code == 404


def test_gasto_rechaza_datos_invalidos(A: Api) -> None:
    assert A("POST", "/gastos", json=_gasto("Malo", "FIJO", "-5")).status_code == 422
    assert A("POST", "/gastos", json=_gasto("Malo", "FIJO", "5", "DECENAL")).status_code == 422
    assert A("POST", "/gastos", json={**_gasto("Malo", "FIJO", "5"), "campo_extra": 1}).status_code == 422
    assert A("POST", "/gastos", json=_gasto("", "FIJO", "5")).status_code == 422


# --------------------------------------------------------------------------- 6 · equipos


def _equipo(nombre: str = "Sillón dental", precio: str = "36000", residual: str = "0", vida: int = 10) -> dict[str, Any]:
    return {
        "nombre": nombre,
        "precio_adquisicion": precio,
        "valor_residual": residual,
        "vida_util_anios": vida,
        "fecha_alta_en_servicio": "2024-01-15",
        "estado": "ACTIVO",
    }


def test_equipo_se_crea_con_su_depreciacion_exacta(A: Api) -> None:
    r = A("POST", "/equipos", json=_equipo(), estado=201)
    assert d(r.json()["depreciacion_mensual"]) == 300  # 36,000 / (10 años × 12 meses)
    ESTADO["equipo"] = r.json()
    assert any(e["identificador"] == r.json()["identificador"] for e in A("GET", "/equipos", estado=200).json()["elementos"])


def test_equipo_se_actualiza_y_detecta_ediciones_simultaneas(A: Api) -> None:
    equipo = E("equipo")
    r = A("PATCH", f"/equipos/{equipo['identificador']}", json=_equipo(), rev=equipo["revision"], estado=200)
    ESTADO["equipo"] = r.json()
    comprobar_concurrencia(A, "PATCH", f"/equipos/{equipo['identificador']}", _equipo(), r.json()["revision"])


def test_equipo_rechaza_datos_invalidos(A: Api) -> None:
    assert A("POST", "/equipos", json=_equipo(residual="36000")).status_code == 422  # residual = precio
    assert A("POST", "/equipos", json=_equipo(precio="0")).status_code == 422
    assert A("POST", "/equipos", json=_equipo(vida=0)).status_code == 422
    assert A("POST", "/equipos", json=_equipo(vida=99999)).status_code == 422


def test_equipo_se_elimina(A: Api) -> None:
    e = A("POST", "/equipos", json=_equipo("Temporal", "1000", "0", 2), estado=201).json()
    A("DELETE", f"/equipos/{e['identificador']}", rev=e["revision"], estado=204)
    assert A("DELETE", f"/equipos/{e['identificador']}", rev=e["revision"]).status_code == 404


def test_resumen_de_costos_indirectos_suma_gastos_y_depreciacion(A: Api) -> None:
    E("equipo"), E("gasto_fijo")
    r = A("GET", "/costos-indirectos/resumen", estado=200).json()
    ESTADO["resumen_costos"] = r
    pool = buscar(r, "pool_mensual") or buscar(r, "total_costos_indirectos") or buscar(r, "total_mensual")
    assert pool is not None, f"no encontré el total en la respuesta: {list(r)}"
    assert d(pool) == 7800  # 6,200 fijos + 1,300 variables + 300 de depreciación


# --------------------------------------------------------------------------- 7 · insumos


def _insumo(nombre: str, unidad: str = "PZA", cantidad: str = "100", precio: str = "180") -> dict[str, Any]:
    return {"nombre": nombre, "presentacion": "Caja", "codigo_unidad": unidad, "cantidad_contenida": cantidad, "precio_presentacion": precio}


def test_catalogo_de_unidades(A: Api) -> None:
    unidades = A("GET", "/unidades-medida", estado=200).json()["elementos"]
    assert len(unidades) == 14 and "PZA" in {u["codigo"] for u in unidades}


def test_insumo_se_crea_con_su_costo_unitario(A: Api) -> None:
    r = A("POST", "/insumos", json=_insumo("Guantes de nitrilo"), estado=201)
    assert d(r.json()["costo_unitario"]) == Decimal("1.8")  # 180 / 100
    ESTADO["insumo"] = r.json()
    A("POST", "/insumos", json=_insumo("Resina compuesta", "G", "4", "600"), estado=201)


def test_insumo_duplicado_es_409_y_unidad_inexistente_es_422(A: Api) -> None:
    assert A("POST", "/insumos", json=_insumo("Guantes de nitrilo")).status_code == 409
    r = A("POST", "/insumos", json=_insumo("Con unidad rara", unidad="XYZ"))
    assert r.status_code == 422, f"unidad inexistente → {r.status_code} {r.json()['detalle']['codigo']}"
    assert A("POST", "/insumos", json=_insumo("Sin contenido", cantidad="0")).status_code == 422
    assert A("POST", "/insumos", json=_insumo("Precio negativo", precio="-1")).status_code == 422


def test_insumos_se_listan_y_se_buscan(A: Api) -> None:
    todos = A("GET", "/insumos", estado=200).json()["elementos"]
    assert len(todos) >= 2
    buscados = A("GET", "/insumos?busqueda=guantes", estado=200).json()["elementos"]
    assert [i["nombre"] for i in buscados] == ["Guantes de nitrilo"]
    assert A("GET", "/insumos?limite=1", estado=200).json()["elementos"].__len__() == 1


def test_cambiar_el_precio_de_un_insumo_agrega_historial(A: Api) -> None:
    insumo = E("insumo")
    r = A("PATCH", f"/insumos/{insumo['identificador']}", json=_insumo("Guantes de nitrilo", precio="200"), rev=insumo["revision"], estado=200)
    assert d(r.json()["costo_unitario"]) == 2  # 200 / 100
    ESTADO["insumo"] = r.json()
    precios = A("GET", f"/insumos/{insumo['identificador']}/precios", estado=200).json()["elementos"]
    assert [d(p["precio_presentacion"]) for p in precios] == [200, 180]  # el más reciente primero
    comprobar_concurrencia(A, "PATCH", f"/insumos/{insumo['identificador']}", _insumo("Guantes de nitrilo", precio="200"), r.json()["revision"])


def test_renombrar_un_insumo_con_un_nombre_ya_usado_es_409(A: Api) -> None:
    resina = next(i for i in A("GET", "/insumos").json()["elementos"] if i["nombre"] == "Resina compuesta")
    r = A("PATCH", f"/insumos/{resina['identificador']}", json=_insumo("Guantes de nitrilo", "G", "4", "600"), rev=resina["revision"])
    assert r.status_code == 409, f"{r.status_code} {r.text[:200]}"


def test_insumo_se_archiva_y_se_restaura(A: Api) -> None:
    resina = next(i for i in A("GET", "/insumos").json()["elementos"] if i["nombre"] == "Resina compuesta")
    r = A("POST", f"/insumos/{resina['identificador']}/archivar", rev=resina["revision"], estado=200)
    assert r.json()["archivado"] is True
    assert resina["identificador"] not in {i["identificador"] for i in A("GET", "/insumos").json()["elementos"]}
    assert resina["identificador"] in {i["identificador"] for i in A("GET", "/insumos?archivados=true").json()["elementos"]}
    r = A("POST", f"/insumos/{resina['identificador']}/restaurar", rev=r.json()["revision"], estado=200)
    assert r.json()["archivado"] is False


def test_insumo_sin_uso_se_elimina(A: Api) -> None:
    i = A("POST", "/insumos", json=_insumo("Temporal"), estado=201).json()
    comprobar_concurrencia(A, "DELETE", f"/insumos/{i['identificador']}", None, i["revision"])
    A("DELETE", f"/insumos/{i['identificador']}", rev=i["revision"], estado=204)
    assert A("DELETE", f"/insumos/{i['identificador']}", rev=i["revision"]).status_code == 404


# --------------------------------------------------------------------------- 8 · periodos mensuales


def _periodo(mes: date, consumo: str, tratamientos: int, procedencia: str = "ESTE_MES") -> dict[str, Any]:
    return {"mes": str(mes), "consumo_materiales": consumo, "tratamientos_atendidos": tratamientos, "procedencia": procedencia, "notas": None}


def test_periodos_mensuales_se_capturan(A: Api) -> None:
    for clave, mes, consumo, n, origen in [
        ("p0", MES_0, "600", 3, "ESTE_MES"), ("p1", MES_1, "400", 4, "PERIODO_ANTERIOR"), ("p2", MES_2, "300", 3, "PERIODO_ANTERIOR"),
    ]:
        ESTADO[clave] = A("POST", "/periodos-mensuales", json=_periodo(mes, consumo, n, origen), estado=201).json()
    assert d(ESTADO["p0"]["materiales_por_tratamiento"]) == 200
    assert A("POST", "/periodos-mensuales", json=_periodo(MES_0, "1", 1)).status_code == 409  # el mes ya existe
    assert A("POST", "/periodos-mensuales", json=_periodo(MES_0.replace(day=15), "1", 1)).status_code == 422
    assert len(A("GET", "/periodos-mensuales", estado=200).json()["elementos"]) == 3


def test_periodo_se_consulta_por_identificador(A: Api) -> None:
    p = E("p0")
    assert A("GET", f"/periodos-mensuales/{p['identificador']}", estado=200).json()["estado"] == "VIGENTE"
    assert A("GET", "/periodos-mensuales/00000000-0000-4000-8000-000000000000").status_code == 404


def test_promedio_de_materiales_es_ponderado(A: Api) -> None:
    E("p2")
    r = A("GET", "/periodos-mensuales/promedio-materiales", estado=200).json()
    # (600 + 400 + 300) / (3 + 4 + 3) = 130; el promedio de promedios daría 133.33
    assert d(r["importe_por_tratamiento"]) == 130
    assert r["madurez"] == "MADURA" and len(r["periodos_incluidos"]) == 3


def test_periodo_se_corrige_se_anula_y_se_restaura(A: Api) -> None:
    p = E("p2")
    corregido = A(
        "POST", f"/periodos-mensuales/{p['identificador']}/correcciones", json={"consumo_materiales": "350", "tratamientos_atendidos": 3, "procedencia": "PERIODO_ANTERIOR", "notas": "ajuste"},
        rev=p["revision"], estado=201,
    ).json()
    assert corregido["numero_version"] == 2 and d(corregido["consumo_materiales"]) == 350
    comprobar_concurrencia(A, "POST", f"/periodos-mensuales/{p['identificador']}/correcciones", {"consumo_materiales": "1", "tratamientos_atendidos": 1, "procedencia": "ESTE_MES"}, corregido["revision"])
    anulado = A("POST", f"/periodos-mensuales/{p['identificador']}/anular", rev=corregido["revision"], estado=200).json()
    assert anulado["estado"] == "ANULADO"
    assert len(A("GET", "/periodos-mensuales/promedio-materiales").json()["periodos_incluidos"]) == 2
    restaurado = A("POST", f"/periodos-mensuales/{p['identificador']}/restaurar", rev=anulado["revision"], estado=200).json()
    assert restaurado["estado"] == "VIGENTE" and d(restaurado["consumo_materiales"]) == 350
    ESTADO["p2"] = restaurado
    ESTADO["promedio_esperado"] = d("1350") / d(10)  # (600 + 400 + 350) / (3 + 4 + 3)


def test_restaurar_un_periodo_que_no_esta_anulado_no_debe_aceptarse(A: Api) -> None:
    p = A("GET", f"/periodos-mensuales/{E('p0')['identificador']}", estado=200).json()
    r = A("POST", f"/periodos-mensuales/{p['identificador']}/restaurar", rev=p["revision"])
    assert r.status_code in (409, 422), f"restaurar un periodo vigente devolvió {r.status_code}"


# --------------------------------------------------------------------------- 9 · plantillas


def test_catalogo_de_plantillas_y_sus_filtros(A: Api) -> None:
    todas = A("GET", "/plantillas-tratamiento", estado=200).json()["elementos"]
    assert len(todas) == 100
    generales = A("GET", "/plantillas-tratamiento?especialidad=GENERAL", estado=200).json()["elementos"]
    assert len(generales) == 10 and all(p["especialidad"] == "GENERAL" for p in generales)
    propias = A("GET", "/plantillas-tratamiento?mis_areas=true", estado=200).json()["elementos"]
    assert 0 < len(propias) < 100  # solo las especialidades elegidas en el perfil
    ESTADO["claves_plantilla"] = [p["clave"] for p in generales[:2]]


def test_importar_plantillas_crea_borradores_sin_duplicar(A: Api) -> None:
    claves = E("claves_plantilla")
    cuerpo = {"claves": claves, "version_catalogo": "2026-09-16.1"}
    r = A("POST", "/tratamientos/importar-plantillas", json=cuerpo, estado=201).json()["elementos"]
    assert len(r) == 2 and all(t["estado"] == "BORRADOR" for t in r)
    otra = A("POST", "/tratamientos/importar-plantillas", json=cuerpo, estado=201).json()["elementos"]
    assert [t["identificador"] for t in otra] == [t["identificador"] for t in r]  # no se duplican
    ESTADO["importados"] = r
    assert A("POST", "/tratamientos/importar-plantillas", json={**cuerpo, "version_catalogo": "1999-01-01"}).status_code == 422
    assert A("POST", "/tratamientos/importar-plantillas", json={"claves": [], "version_catalogo": "2026-09-16.1"}).status_code == 422


def test_materiales_sugeridos_se_vinculan_a_un_insumo(A: Api) -> None:
    sugeridos = A("GET", "/tratamientos/materiales-sugeridos", estado=200).json()["elementos"]
    assert sugeridos, "las plantillas importadas no trajeron materiales sugeridos"
    primero = sugeridos[0]
    insumo = E("insumo")
    r = A(
        "POST",
        "/tratamientos/materiales-sugeridos/vincular",
        json={
            "nombre_generico": primero["nombre_generico"],
            "identificador_insumo": insumo["identificador"],
            "cantidades": [{"identificador_tratamiento": t, "cantidad": "2"} for t in primero["identificadores_tratamientos"]],
        },
        estado=200,
    )
    assert r.json()["tratamientos_actualizados"] >= 1
    restantes = {s["nombre_generico"] for s in A("GET", "/tratamientos/materiales-sugeridos").json()["elementos"]}
    assert primero["nombre_generico"] not in restantes  # ya está vinculado
    ajeno = A("POST", "/tratamientos/materiales-sugeridos/vincular", json={"nombre_generico": "x", "identificador_insumo": "00000000-0000-4000-8000-000000000000", "cantidades": []})
    assert ajeno.status_code == 422


# --------------------------------------------------------------------------- 10 · tratamientos


def _config(nombre: str, **cambios: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "nombre": nombre, "especialidad": "GENERAL", "duracion_clinica": 30, "espaciado": None,
        "metodo_materiales": None, "importe_materiales": None, "receta": [], "ajuste_porcentaje": "30",
    }
    base.update(cambios)
    return base


def _detalle(A: Api, clave: str) -> dict[str, Any]:
    return A("GET", f"/tratamientos/{E(clave)['identificador']}", estado=200).json()


def test_tratamiento_se_crea_con_clave_de_idempotencia(A: Api) -> None:
    cuerpo = {"nombre": "Limpieza dental (humo)", "especialidad": "GENERAL", "duracion_clinica": 30}
    clave = clave_nueva()
    t1 = A("POST", "/tratamientos", json=cuerpo, clave=clave, estado=201).json()
    repetido = A("POST", "/tratamientos", json=cuerpo, clave=clave, estado=201).json()
    assert repetido["identificador"] == t1["identificador"]  # el reintento devuelve el mismo
    assert A("POST", "/tratamientos", json=cuerpo).status_code == 422  # falta la clave
    assert A("POST", "/tratamientos", json={**cuerpo, "nombre": "Otro"}, clave=clave).status_code in (409, 422)
    assert A("POST", "/tratamientos", json={**cuerpo, "duracion_clinica": 0}, clave=clave_nueva()).status_code == 422
    ESTADO["t1"] = t1
    ESTADO["t2"] = A("POST", "/tratamientos", json={**cuerpo, "nombre": "Resina con receta (humo)"}, clave=clave_nueva(), estado=201).json()
    ESTADO["t3"] = A("POST", "/tratamientos", json={**cuerpo, "nombre": "Blanqueamiento (humo)"}, clave=clave_nueva(), estado=201).json()


def test_tratamientos_se_listan_se_filtran_y_se_consultan(A: Api) -> None:
    assert len(A("GET", "/tratamientos", estado=200).json()["elementos"]) >= 5
    assert any("Resina" in t["nombre"] for t in A("GET", "/tratamientos?busqueda=resina", estado=200).json()["elementos"])
    assert A("GET", "/tratamientos?estado=BORRADOR", estado=200).json()["elementos"]
    assert A("GET", "/tratamientos?estado=", estado=200)  # filtro vacío = sin filtro
    assert A("GET", "/tratamientos?archivados=true", estado=200)
    assert A("GET", "/tratamientos?limite=0").status_code == 422
    assert A("GET", f"/tratamientos/{E('t1')['identificador']}", estado=200).json()["estado"] == "BORRADOR"
    assert A("GET", "/tratamientos/00000000-0000-4000-8000-000000000000").status_code == 404


def test_un_tratamiento_sin_configurar_no_se_calcula_y_explica_que_falta(A: Api) -> None:
    det = _detalle(A, "t1")
    r = A("POST", f"/tratamientos/{det['identificador']}/calculos", json={"revision_tratamiento": det["revision"]}, rev=det["revision"], clave=clave_nueva())
    assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"
    detalle = r.json()["detalle"]
    assert detalle["codigo"] == "CALCULO_BLOQUEADO" and detalle["bloqueos"]
    assert all({"codigo", "paso", "mensaje"} <= set(b) for b in detalle["bloqueos"])


def test_configuracion_con_importe_rapido(A: Api) -> None:
    det = _detalle(A, "t1")
    r = A("PUT", f"/tratamientos/{det['identificador']}/configuracion", json=_config("Limpieza dental (humo)", metodo_materiales="IMPORTE_RAPIDO", importe_materiales="20"), rev=det["revision"], estado=200)
    assert r.json()["metodo_materiales"] == "IMPORTE_RAPIDO" and d(r.json()["importe_materiales"]) == 20
    assert r.json()["revision"] == det["revision"] + 1
    comprobar_concurrencia(A, "PUT", f"/tratamientos/{det['identificador']}/configuracion", _config("x"), r.json()["revision"])
    assert A("PUT", f"/tratamientos/{det['identificador']}/configuracion", json=_config("x", ajuste_porcentaje="0"), rev=r.json()["revision"]).status_code == 422
    assert A("PUT", f"/tratamientos/{det['identificador']}/configuracion", json=_config("x", duracion_clinica=601), rev=r.json()["revision"]).status_code == 422


def test_la_vista_previa_calcula_sin_guardar_nada(A: Api) -> None:
    det = _detalle(A, "t1")
    base = A("POST", f"/tratamientos/{det['identificador']}/vista-previa", json={}, estado=200).json()
    assert d(buscar(base, "precio_sugerido")) == 100 and d(buscar(base, "costo_total")) == 60
    alterno = A("POST", f"/tratamientos/{det['identificador']}/vista-previa", json={"configuracion": _config("x", metodo_materiales="IMPORTE_RAPIDO", importe_materiales="100")}, estado=200).json()
    assert d(buscar(alterno, "costo_total")) == 140 and d(buscar(alterno, "precio_sugerido")) == 200
    despues = _detalle(A, "t1")
    assert despues["revision"] == det["revision"] and d(despues["importe_materiales"]) == 20  # nada cambió
    assert A("GET", f"/tratamientos/{det['identificador']}/hojas-costos", estado=200).json()["elementos"] == []


def test_calcular_con_importe_rapido_da_el_caso_base_del_manual(A: Api) -> None:
    det = _detalle(A, "t1")
    ruta = f"/tratamientos/{det['identificador']}/calculos"
    cuerpo = {"revision_tratamiento": det["revision"]}
    clave = clave_nueva()
    hoja = A("POST", ruta, json=cuerpo, rev=det["revision"], clave=clave, estado=201).json()
    # Pool 7,800 → costo por minuto $1; (30 + 10) min = 40; + 20 de materiales = 60; ×1.30 = 78 → $100
    resultado = hoja["resultado"]
    assert d(resultado["costo_total"]) == 60 and d(resultado["precio_sugerido"]) == 100 and d(resultado["margen_porcentaje"]) == 40
    assert resultado["semaforo"] == "INTERMEDIO"
    ESTADO["hoja_1"] = hoja
    assert A("POST", ruta, json=cuerpo, rev=det["revision"], clave=clave, estado=201).json()["identificador"] == hoja["identificador"]
    assert A("POST", ruta, json={"revision_tratamiento": det["revision"] + 99}, rev=det["revision"] + 99, clave=clave_nueva()).status_code == 409
    assert A("POST", ruta, json=cuerpo, rev=det["revision"] + 99, clave=clave_nueva()).status_code == 428  # encabezado y cuerpo no coinciden
    assert A("POST", ruta, json=cuerpo, clave=clave_nueva()).status_code == 428
    assert A("POST", ruta, json=cuerpo, rev=det["revision"]).status_code == 422  # falta Idempotency-Key
    calculado = _detalle(A, "t1")
    assert calculado["estado"] == "CALCULADO" and d(calculado["ultimo_resultado"]["precio_sugerido"]) == 100


def test_historial_de_hojas_de_costos(A: Api) -> None:
    hoja = E("hoja_1")
    t = E("t1")["identificador"]
    lista = A("GET", f"/tratamientos/{t}/hojas-costos", estado=200).json()["elementos"]
    assert [h["identificador"] for h in lista] == [hoja["identificador"]]
    detalle = A("GET", f"/hojas-costos/{hoja['identificador']}", estado=200).json()
    assert detalle["identificador"] == hoja["identificador"]
    assert A("GET", "/hojas-costos/00000000-0000-4000-8000-000000000000").status_code == 404


def test_receta_de_insumos_aplica_precio_unitario_y_merma(A: Api) -> None:
    insumo, det = E("insumo"), _detalle(A, "t2")
    cfg = _config("Resina con receta (humo)", metodo_materiales="RECETA_INSUMOS", receta=[{"identificador_insumo": insumo["identificador"], "cantidad": "2", "merma_porcentaje": "10"}])
    r = A("PUT", f"/tratamientos/{det['identificador']}/configuracion", json=cfg, rev=det["revision"], estado=200).json()
    assert len(r["receta"]) == 1
    hoja = A("POST", f"/tratamientos/{det['identificador']}/calculos", json={"revision_tratamiento": r["revision"]}, rev=r["revision"], clave=clave_nueva(), estado=201).json()
    # Guantes a $2.00 c/u (200 ÷ 100): 2 pzas con 10 % de merma = 4.40; costo = 40 + 4.40
    assert d(hoja["resultado"]["costo_total"]) == Decimal("44.40")
    ESTADO["hoja_2"] = hoja


def test_un_insumo_usado_en_una_receta_no_se_puede_eliminar(A: Api) -> None:
    insumo = A("GET", "/insumos?busqueda=guantes", estado=200).json()["elementos"][0]
    r = A("DELETE", f"/insumos/{insumo['identificador']}", rev=insumo["revision"])
    assert r.status_code == 409 and r.json()["detalle"]["codigo"] == "INSUMO_EN_USO"


def test_una_receta_con_un_insumo_archivado_se_bloquea_en_lugar_de_subestimar_el_precio(A: Api) -> None:
    guantes = A("GET", "/insumos?busqueda=guantes", estado=200).json()["elementos"][0]  # $2.00 por pieza
    mascarilla = A("POST", "/insumos", json=_insumo("Mascarilla (humo)", cantidad="50", precio="50"), estado=201).json()  # $1.00
    t = A("POST", "/tratamientos", json={"nombre": "Receta con dos insumos (humo)", "especialidad": "GENERAL", "duracion_clinica": 30}, clave=clave_nueva(), estado=201).json()
    linea = lambda i: {"identificador_insumo": i["identificador"], "cantidad": "1", "merma_porcentaje": "0"}  # noqa: E731
    cfg = _config("Receta con dos insumos (humo)", metodo_materiales="RECETA_INSUMOS", receta=[linea(guantes), linea(mascarilla)])
    ruta = f"/tratamientos/{t['identificador']}"
    r = A("PUT", ruta + "/configuracion", json=cfg, rev=t["revision"], estado=200).json()
    completa = A("POST", ruta + "/calculos", json={"revision_tratamiento": r["revision"]}, rev=r["revision"], clave=clave_nueva(), estado=201).json()
    assert d(completa["resultado"]["costo_total"]) == 43  # 40 de tiempo + 2.00 + 1.00
    # Se archiva uno de los dos insumos: el cálculo NO debe seguir como si la línea no existiera.
    archivada = A("POST", f"/insumos/{mascarilla['identificador']}/archivar", rev=mascarilla["revision"], estado=200).json()
    det = A("GET", ruta, estado=200).json()
    assert det["estado"] == "CAMBIOS_POR_REVISAR"
    r = A("POST", ruta + "/calculos", json={"revision_tratamiento": det["revision"]}, rev=det["revision"], clave=clave_nueva())
    assert r.status_code == 422, f"con un insumo archivado se calculó igual ({r.status_code}): {r.text[:200]}"
    assert any(b["codigo"] == "RECETA_INCOMPLETA" for b in r.json()["detalle"]["bloqueos"])
    previa = A("POST", ruta + "/vista-previa", json={}, estado=200).json()
    assert previa["estado"] == "borrador" and previa["resultado"] is None
    # La vista previa con la receta editada en pantalla (sin guardar) también lo detecta.
    editada = A("POST", ruta + "/vista-previa", json={"configuracion": cfg}, estado=200).json()
    assert editada["estado"] == "borrador"
    # Al restaurar el insumo vuelve a calcularse con el mismo resultado.
    A("POST", f"/insumos/{mascarilla['identificador']}/restaurar", rev=archivada["revision"], estado=200)
    det = A("GET", ruta, estado=200).json()
    de_nuevo = A("POST", ruta + "/calculos", json={"revision_tratamiento": det["revision"]}, rev=det["revision"], clave=clave_nueva(), estado=201).json()
    assert d(de_nuevo["resultado"]["costo_total"]) == 43


def test_receta_rechaza_insumos_invalidos_o_repetidos_sin_error_500(A: Api) -> None:
    insumo, det = E("insumo"), _detalle(A, "t2")
    ruta = f"/tratamientos/{det['identificador']}/configuracion"
    linea = {"identificador_insumo": insumo["identificador"], "cantidad": "1", "merma_porcentaje": "0"}
    inexistente = _config("x", metodo_materiales="RECETA_INSUMOS", receta=[{**linea, "identificador_insumo": "00000000-0000-4000-8000-000000000000"}])
    assert A("PUT", ruta, json=inexistente, rev=det["revision"]).status_code == 422
    repetida = _config("Resina con receta (humo)", metodo_materiales="RECETA_INSUMOS", receta=[linea, linea])
    r = A("PUT", ruta, json=repetida, rev=det["revision"])
    assert r.status_code in (200, 422), f"insumo repetido en la receta → {r.status_code} {r.text[:200]}"


def test_promedio_de_mis_meses_alimenta_el_costo_de_materiales(A: Api) -> None:
    esperado, det = E("promedio_esperado"), _detalle(A, "t3")
    r = A("PUT", f"/tratamientos/{det['identificador']}/configuracion", json=_config("Blanqueamiento (humo)", metodo_materiales="PROMEDIO_MENSUAL"), rev=det["revision"], estado=200).json()
    hoja = A("POST", f"/tratamientos/{det['identificador']}/calculos", json={"revision_tratamiento": r["revision"]}, rev=r["revision"], clave=clave_nueva(), estado=201).json()
    assert d(hoja["resultado"]["costo_total"]) == 40 + esperado  # tiempo + (600+400+350)/(3+4+3)
    assert d(A("GET", "/periodos-mensuales/promedio-materiales").json()["importe_por_tratamiento"]) == esperado


def test_cambiar_un_gasto_marca_los_precios_como_por_revisar_y_se_recalculan(A: Api) -> None:
    fijo = E("gasto_fijo")
    actual = next(g for g in A("GET", "/gastos").json()["elementos"] if g["identificador"] == fijo["identificador"])
    A("PATCH", f"/gastos/{fijo['identificador']}", json=_gasto("Renta", "FIJO", "6200"), rev=actual["revision"], estado=200)
    assert _detalle(A, "t1")["estado"] == "CAMBIOS_POR_REVISAR"
    assert A("GET", "/inicio/resumen", estado=200).json()["siguiente_paso"]["codigo"] == "REVISAR_CAMBIOS"
    det = _detalle(A, "t1")
    nueva = A("POST", f"/tratamientos/{det['identificador']}/calculos", json={"revision_tratamiento": det["revision"]}, rev=det["revision"], clave=clave_nueva(), estado=201).json()
    assert _detalle(A, "t1")["estado"] == "CALCULADO"
    assert len(A("GET", f"/tratamientos/{det['identificador']}/hojas-costos").json()["elementos"]) == 2
    assert buscar(nueva, "sustituye_a") == E("hoja_1")["identificador"]  # la hoja nueva reemplaza a la anterior


def test_tratamiento_se_archiva_y_se_restaura(A: Api) -> None:
    t = A("POST", "/tratamientos", json={"nombre": "Temporal (humo)", "especialidad": "GENERAL", "duracion_clinica": 20}, clave=clave_nueva(), estado=201).json()
    ruta = f"/tratamientos/{t['identificador']}"
    comprobar_concurrencia(A, "POST", ruta + "/archivar", None, t["revision"])
    archivado = A("POST", ruta + "/archivar", rev=t["revision"], estado=200).json()
    assert archivado["estado"] == "ARCHIVADO"
    assert t["identificador"] not in {x["identificador"] for x in A("GET", "/tratamientos").json()["elementos"]}
    assert t["identificador"] in {x["identificador"] for x in A("GET", "/tratamientos?archivados=true").json()["elementos"]}
    restaurado = A("POST", ruta + "/restaurar", rev=archivado["revision"], estado=200).json()
    assert restaurado["estado"] == "BORRADOR"  # nunca se calculó
    ESTADO["t_temporal"] = restaurado


def test_restaurar_un_tratamiento_con_precio_pide_revisarlo(A: Api) -> None:
    det = _detalle(A, "t1")
    archivado = A("POST", f"/tratamientos/{det['identificador']}/archivar", rev=det["revision"], estado=200).json()
    restaurado = A("POST", f"/tratamientos/{det['identificador']}/restaurar", rev=archivado["revision"], estado=200).json()
    assert restaurado["estado"] == "CAMBIOS_POR_REVISAR"  # no se presenta como vigente un precio posiblemente viejo


def test_un_tratamiento_archivado_no_se_desarchiva_al_editarlo(A: Api) -> None:
    t = A("POST", "/tratamientos", json={"nombre": "Archivado (humo)", "especialidad": "GENERAL", "duracion_clinica": 20}, clave=clave_nueva(), estado=201).json()
    archivado = A("POST", f"/tratamientos/{t['identificador']}/archivar", rev=t["revision"], estado=200).json()
    r = A("PUT", f"/tratamientos/{t['identificador']}/configuracion", json=_config("Archivado (humo)", metodo_materiales="IMPORTE_RAPIDO", importe_materiales="5"), rev=archivado["revision"])
    estado = r.json()["estado"] if r.status_code == 200 else None
    assert r.status_code == 422 or estado == "ARCHIVADO", f"editar un tratamiento archivado devolvió {r.status_code} y estado {estado}"
    # Calcularlo tampoco debe desarchivarlo.
    actual = A("GET", f"/tratamientos/{t['identificador']}", estado=200).json()
    assert actual["estado"] == "ARCHIVADO"
    ruta = f"/tratamientos/{t['identificador']}/calculos"
    r = A("POST", ruta, json={"revision_tratamiento": actual["revision"]}, rev=actual["revision"], clave=clave_nueva())
    assert r.status_code == 422, f"calcular un tratamiento archivado devolvió {r.status_code}"
    assert A("GET", f"/tratamientos/{t['identificador']}", estado=200).json()["estado"] == "ARCHIVADO"


# --------------------------------------------------------------------------- 11 · inicio


def test_resumen_de_inicio(A: Api) -> None:
    r = A("GET", "/inicio/resumen", estado=200).json()
    kpi = r["kpi"]
    assert kpi["total"] >= 4 and kpi["con_calculo"] + kpi["pendientes"] == kpi["total"]
    assert r["ultimo_resultado"] is not None and 1 <= len(r["recientes"]) <= 5
    assert r["siguiente_paso"]["codigo"] in {"CREAR_TRATAMIENTO", "REGISTRAR_TIEMPO", "REGISTRAR_COSTOS", "REVISAR_CAMBIOS", "CALCULAR_TRATAMIENTO", "TODO_LISTO"}


def test_un_consultorio_nuevo_ve_su_inicio_vacio(B: Api) -> None:
    r = B("GET", "/inicio/resumen", estado=200).json()
    assert r["kpi"] == {"con_calculo": 0, "pendientes": 0, "total": 0}
    assert r["siguiente_paso"]["codigo"] == "CREAR_TRATAMIENTO" and r["ultimo_resultado"] is None


# --------------------------------------------------------------------------- 12 · aislamiento entre consultorios


def test_otro_consultorio_no_ve_ni_modifica_los_datos(A: Api, B: Api) -> None:
    gasto, equipo, insumo = E("gasto_fijo"), E("equipo"), E("insumo")
    periodo, t1, hoja = E("p0"), E("t1"), E("hoja_1")
    vivo = lambda api, ruta: api("GET", ruta).json()  # noqa: E731
    # Listas: el otro consultorio parte vacío
    for ruta in ("/gastos", "/equipos", "/insumos", "/periodos-mensuales", "/tratamientos"):
        assert B("GET", ruta, estado=200).json()["elementos"] == [], f"B ve datos de A en {ruta}"
    assert B("GET", "/perfil-capacidad").status_code == 404
    assert B("GET", "/costos-indirectos/resumen", estado=200)
    # Lecturas por identificador
    for ruta in (
        f"/insumos/{insumo['identificador']}/precios",
        f"/periodos-mensuales/{periodo['identificador']}",
        f"/tratamientos/{t1['identificador']}",
        f"/hojas-costos/{hoja['identificador']}",
    ):
        assert B("GET", ruta).status_code == 404, ruta
    assert B("GET", f"/tratamientos/{t1['identificador']}/hojas-costos").json().get("elementos", []) == []
    # Escrituras sobre recursos ajenos
    escrituras = [
        ("PATCH", f"/gastos/{gasto['identificador']}", _gasto("x", "FIJO", "1")),
        ("DELETE", f"/gastos/{gasto['identificador']}", None),
        ("PATCH", f"/equipos/{equipo['identificador']}", _equipo()),
        ("DELETE", f"/equipos/{equipo['identificador']}", None),
        ("PATCH", f"/insumos/{insumo['identificador']}", _insumo("x")),
        ("DELETE", f"/insumos/{insumo['identificador']}", None),
        ("POST", f"/insumos/{insumo['identificador']}/archivar", None),
        ("POST", f"/insumos/{insumo['identificador']}/restaurar", None),
        ("POST", f"/periodos-mensuales/{periodo['identificador']}/correcciones", {"consumo_materiales": "1", "tratamientos_atendidos": 1, "procedencia": "ESTE_MES"}),
        ("POST", f"/periodos-mensuales/{periodo['identificador']}/anular", None),
        ("POST", f"/periodos-mensuales/{periodo['identificador']}/restaurar", None),
        ("PUT", f"/tratamientos/{t1['identificador']}/configuracion", _config("x")),
        ("POST", f"/tratamientos/{t1['identificador']}/archivar", None),
        ("POST", f"/tratamientos/{t1['identificador']}/restaurar", None),
    ]
    for metodo, ruta, cuerpo in escrituras:
        r = B(metodo, ruta, json=cuerpo, rev=0)
        assert r.status_code == 404, f"{metodo} {ruta} desde otro consultorio devolvió {r.status_code}"
    # Cálculo y vista previa de un tratamiento ajeno
    assert B("POST", f"/tratamientos/{t1['identificador']}/vista-previa", json={}).status_code == 404
    assert B("POST", f"/tratamientos/{t1['identificador']}/calculos", json={"revision_tratamiento": 0}, rev=0, clave=clave_nueva()).status_code == 404
    # No se puede usar un insumo ajeno en una receta
    propio = B("POST", "/tratamientos", json={"nombre": "Propio", "especialidad": "GENERAL", "duracion_clinica": 10}, clave=clave_nueva(), estado=201).json()
    receta = _config("Propio", metodo_materiales="RECETA_INSUMOS", receta=[{"identificador_insumo": insumo["identificador"], "cantidad": "1", "merma_porcentaje": "0"}])
    assert B("PUT", f"/tratamientos/{propio['identificador']}/configuracion", json=receta, rev=propio["revision"]).status_code == 422
    # Y lo de A sigue intacto
    assert vivo(A, f"/insumos/{insumo['identificador']}/precios")["elementos"]


# --------------------------------------------------------------------------- 13 · sesión obligatoria

PUBLICAS = {
    ("GET", "/health"), ("GET", "/ready"), ("POST", "/autenticacion/registro"),
    ("POST", "/autenticacion/inicio-sesion"), ("POST", "/autenticacion/renovacion"),
}
PROTEGIDAS = sorted(CONTRATO.operaciones - PUBLICAS)


@pytest.mark.parametrize(("metodo", "plantilla"), PROTEGIDAS, ids=[f"{m} {p}" for m, p in PROTEGIDAS])
def test_toda_operacion_protegida_exige_sesion(cliente: TestClient, metodo: str, plantilla: str) -> None:
    api = Api(cliente, CONTRATO)
    ruta = re.sub(r"\{[^}]+\}", "00000000-0000-4000-8000-000000000000", plantilla)
    r = api(metodo, ruta, json={} if metodo in ("POST", "PUT", "PATCH") else None, sesion=False)
    assert r.status_code == 401, f"{metodo} {plantilla} sin sesión devolvió {r.status_code}"
    assert r.json()["detalle"]["codigo"] in {"SIN_AUTENTICACION", "TOKEN_VENCIDO"}


def test_un_token_alterado_o_ajeno_se_rechaza(cliente: TestClient, A: Api) -> None:
    api = Api(cliente, CONTRATO)
    for token in ("basura", A.token[:-3] + "abc", ""):  # type: ignore[index]
        r = api("GET", "/perfil", encabezados={"Authorization": f"Bearer {token}"}, sesion=False)
        assert r.status_code == 401, token


# --------------------------------------------------------------------------- 14 · verificaciones finales


def test_las_56_operaciones_del_contrato_se_ejercitaron_con_exito() -> None:
    faltantes = CONTRATO.sin_ejercitar()
    assert not faltantes, f"{len(faltantes)} de {len(CONTRATO.operaciones)} operaciones sin una llamada exitosa: {faltantes}"


def test_las_respuestas_cumplen_el_contrato_openapi() -> None:
    unicos = sorted(set(CONTRATO.incumplimientos))
    if os.getenv("MEDALYZE_VOLCAR_INCUMPLIMIENTOS"):
        Path(os.environ["MEDALYZE_VOLCAR_INCUMPLIMIENTOS"]).write_text("\n".join(unicos) + "\n", encoding="utf-8")
    assert not unicos, f"{len(unicos)} incumplimientos del contrato:\n" + "\n".join(unicos[:60])


def test_los_estados_devueltos_estan_documentados_en_el_contrato() -> None:
    unicos = sorted(set(CONTRATO.no_documentados))
    if os.getenv("MEDALYZE_VOLCAR_INCUMPLIMIENTOS"):
        Path(os.environ["MEDALYZE_VOLCAR_INCUMPLIMIENTOS"] + ".estados").write_text("\n".join(unicos) + "\n", encoding="utf-8")
    assert not unicos, "\n".join(unicos)
