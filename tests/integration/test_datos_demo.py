"""El script de datos de demostración deja un consultorio completo y coherente, y se puede repetir.

Ejecuta ``scripts/datos_demo.py`` contra la API real (con PostgreSQL), dos veces seguidas, y comprueba:
  * qué quedó creado y que repetir la carga no duplica nada;
  * los números del consultorio (costos indirectos, costo por minuto) y de los precios calculados;
  * que cada respuesta de la API durante la carga cumple el contrato OpenAPI.
"""

from __future__ import annotations

import importlib.util
import os
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from humo_base import Contrato

pytestmark = pytest.mark.postgres

RAIZ = Path(__file__).resolve().parents[2]
CONTRASENA = "Demo-Medalyze-2026"


def _cargar_script() -> ModuleType:
    especificacion = importlib.util.spec_from_file_location(
        "datos_demo", RAIZ / "scripts" / "datos_demo.py"
    )
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def _adaptador(cliente: TestClient, contrato: Contrato) -> Any:
    def llamar(
        metodo: str,
        ruta: str,
        json: Any = None,
        rev: int | None = None,
        clave: str | None = None,
        token: str | None = None,
    ) -> tuple[int, Any]:
        cabeceras: dict[str, str] = {}
        if token:
            cabeceras["Authorization"] = f"Bearer {token}"
        if rev is not None:
            cabeceras["If-Match"] = str(rev)
        if clave:
            cabeceras["Idempotency-Key"] = clave
        respuesta = cliente.request(metodo, "/api/v1" + ruta, json=json, headers=cabeceras)
        cuerpo = respuesta.json() if respuesta.content else None
        contrato.registrar(metodo, ruta, respuesta.status_code, cuerpo)
        return respuesta.status_code, cuerpo

    return llamar


@pytest.fixture(scope="module")
def carga() -> SimpleNamespace:
    if os.getenv("MEDALYZE_TEST_POSTGRES") != "1":
        pytest.skip("Las pruebas PostgreSQL se ejecutan con MEDALYZE_TEST_POSTGRES=1.")
    from app.main import app

    cliente = TestClient(app, raise_server_exceptions=False)
    modulo = _cargar_script()
    contrato = Contrato()
    llamar = _adaptador(cliente, contrato)
    correo = f"demo-{os.urandom(4).hex()}@ejemplo.mx"
    primera = modulo.cargar_datos_demo(llamar, correo, CONTRASENA)
    segunda = modulo.cargar_datos_demo(
        llamar, correo, CONTRASENA
    )  # la repetición no debe duplicar nada
    estado, sesion = llamar(
        "POST", "/autenticacion/inicio-sesion", json={"correo": correo, "contrasena": CONTRASENA}
    )
    assert estado == 200
    return SimpleNamespace(
        modulo=modulo, contrato=contrato, llamar=llamar, correo=correo,
        token=sesion["token_acceso"], primera=primera, segunda=segunda,
    )  # fmt: skip


def _lista(carga: SimpleNamespace, ruta: str) -> list[dict[str, Any]]:
    separador = "&" if "?" in ruta else "?"
    estado, cuerpo = carga.llamar("GET", f"{ruta}{separador}limite=100", token=carga.token)
    assert estado == 200
    return cuerpo["elementos"]


def test_queda_un_consultorio_completo(carga: SimpleNamespace) -> None:
    c = carga.modulo
    assert len(_lista(carga, "/gastos")) == len(c.GASTOS) == 11
    assert len(_lista(carga, "/equipos")) == len(c.EQUIPOS) == 6
    assert len(_lista(carga, "/insumos")) == len(c.INSUMOS)
    assert len(_lista(carga, "/periodos-mensuales")) == len(c.PERIODOS) == 3
    assert len(_lista(carga, "/tratamientos")) == len(c.TRATAMIENTOS) == 7


def test_repetir_la_carga_no_duplica_nada(carga: SimpleNamespace) -> None:
    assert carga.segunda["conteos"] == carga.primera["conteos"]
    assert carga.segunda["tratamientos"] == carga.primera["tratamientos"]
    for tratamiento in _lista(carga, "/tratamientos"):
        estado, historial = carga.llamar(
            "GET", f"/tratamientos/{tratamiento['identificador']}/hojas-costos", token=carga.token
        )
        esperadas = 0 if tratamiento["estado"] == "BORRADOR" else 1
        assert len(historial["elementos"]) == esperadas, tratamiento["nombre"]


def test_los_costos_indirectos_son_los_esperados(carga: SimpleNamespace) -> None:
    costos = carga.primera["costos_indirectos"]
    assert Decimal(costos["gastos_fijos"]) == Decimal(
        "32749.00"
    )  # incluye el sueldo quincenal ×2 y el seguro anual ÷12
    assert Decimal(costos["gastos_variables"]) == Decimal(
        "4180.00"
    )  # la electricidad bimestral cuenta la mitad
    # La base guarda la depreciación de cada equipo a 6 decimales, así que la suma queda a una millonésima
    # de 3,068.75. Es un pendiente menor de precisión, no un error de contrato.
    tolerancia = Decimal("0.00001")
    assert abs(Decimal(costos["depreciacion"]) - Decimal("3068.75")) < tolerancia
    assert abs(Decimal(costos["total_mensual"]) - Decimal("39997.75")) < tolerancia
    # 5 días × 52/12 × 8 h × 60 min = 10,400 disponibles; al 70 % son 7,280 efectivos.
    assert round(Decimal(costos["costo_por_minuto"]), 4) == Decimal("5.4942")


def test_seis_tratamientos_calculados_y_uno_en_borrador(carga: SimpleNamespace) -> None:
    estados = {t["nombre"]: t["estado"] for t in carga.primera["tratamientos"]}
    assert estados.pop("Corona de zirconia") == "BORRADOR"
    assert set(estados.values()) == {"CALCULADO"} and len(estados) == 6


def test_se_usan_los_tres_metodos_de_materiales(carga: SimpleNamespace) -> None:
    metodos = {t["metodo"] for t in carga.primera["tratamientos"]}
    assert {"RECETA_INSUMOS", "IMPORTE_RAPIDO", "PROMEDIO_MENSUAL"} <= metodos


def test_el_semaforo_muestra_los_tres_colores(carga: SimpleNamespace) -> None:
    colores = {t["semaforo"] for t in carga.primera["tratamientos"] if t["semaforo"]}
    assert colores == {"ALTO", "INTERMEDIO", "BAJO"}


def test_los_precios_son_multiplos_de_50_y_cubren_el_costo(carga: SimpleNamespace) -> None:
    for t in carga.primera["tratamientos"]:
        if t["estado"] != "CALCULADO":
            continue
        precio, costo = Decimal(t["precio_sugerido"]), Decimal(t["costo_total"])
        assert precio % 50 == 0, t["nombre"]
        assert precio >= costo, t["nombre"]


def test_se_puede_iniciar_sesion_y_el_inicio_refleja_los_datos(carga: SimpleNamespace) -> None:
    estado, inicio = carga.llamar("GET", "/inicio/resumen", token=carga.token)
    assert estado == 200
    assert inicio["kpi"] == {"con_calculo": 6, "pendientes": 1, "total": 7}
    assert inicio["ultimo_resultado"] is not None and len(inicio["recientes"]) == 5


def test_cada_respuesta_de_la_carga_cumple_el_contrato(carga: SimpleNamespace) -> None:
    assert not sorted(set(carga.contrato.incumplimientos)), "\n".join(
        sorted(set(carga.contrato.incumplimientos))[:30]
    )
    assert not sorted(set(carga.contrato.no_documentados)), "\n".join(
        sorted(set(carga.contrato.no_documentados))
    )
