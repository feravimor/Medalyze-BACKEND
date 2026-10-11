"""El ejemplo numérico oficial (Medalyze_Recorrido_Completo_Ejemplo_Numerico.pdf) reproducido a través de la API.

De $26,000 de costo operativo mensual hasta un precio sugerido de $650 y un margen de 30.77 %, por las tres vías
de materiales. Es la prueba de aceptación de las reglas de costeo: si el documento cambia, cambia esta prueba.
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
D = Decimal


def _script() -> ModuleType:
    especificacion = importlib.util.spec_from_file_location(
        "ejemplo_oficial", RAIZ / "scripts" / "ejemplo_oficial.py"
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
def ejemplo() -> SimpleNamespace:
    if os.getenv("MEDALYZE_TEST_POSTGRES") != "1":
        pytest.skip("Las pruebas PostgreSQL se ejecutan con MEDALYZE_TEST_POSTGRES=1.")
    from app.main import app

    modulo = _script()
    contrato = Contrato()
    obtenido = modulo.ejecutar(_adaptador(TestClient(app, raise_server_exceptions=False), contrato))
    return SimpleNamespace(modulo=modulo, contrato=contrato, **obtenido)


def _num(valor: Any) -> Decimal:
    return D(str(valor)).quantize(D("0.01"))


def test_el_costo_del_consultorio_y_el_costo_por_minuto(ejemplo: SimpleNamespace) -> None:
    costos = ejemplo.costos
    assert _num(costos["gastos_fijos"]) == D("20000")  # renta + asistente ×2 + software ÷12
    assert _num(costos["gastos_variables"]) == D(
        "4000"
    )  # electricidad ÷2 + agua + limpieza + mantenimiento ÷12
    assert _num(costos["depreciacion"]) == D("2000")  # ($120,000 − $0) ÷ (5 × 12)
    assert _num(costos["total_mensual"]) == D("26000")
    assert costos["minutos_disponibles"] == 10400  # 5 × (52 ÷ 12) × 8 × 60
    assert costos["minutos_efectivos"] == 5200  # × 50 %
    assert _num(costos["costo_por_minuto"]) == D("5")


@pytest.mark.parametrize(
    "caso", ["A · Promedio mensual + especial", "B · Receta", "Importe rápido"]
)
def test_las_tres_vias_llegan_al_mismo_precio_del_documento(
    ejemplo: SimpleNamespace, caso: str
) -> None:
    r = ejemplo.casos[caso]
    assert _num(r["costo_tiempo"]) == D("300")  # (50 + 10) × $5
    assert _num(D(str(r["materiales_generales"])) + D(str(r["materiales_especiales"]))) == D("150")
    assert _num(r["costo_total"]) == D("450")
    assert _num(r["ajuste_porcentaje"]) == D("40")
    assert _num(r["importe_ajustado"]) == D("630")  # $450 × 1.40
    assert _num(r["precio_sugerido"]) == D("650")  # hacia arriba al múltiplo de $50
    assert _num(r["margen_porcentaje"]) == D(
        "30.77"
    )  # ($650 − $450) ÷ $650: no es el 40 % del incremento
    assert r["semaforo"] == "INTERMEDIO"


def test_el_promedio_mensual_suma_el_especial_aparte(ejemplo: SimpleNamespace) -> None:
    r = ejemplo.casos["A · Promedio mensual + especial"]
    assert _num(r["materiales_generales"]) == D(
        "100"
    )  # ($6,000 + $12,000 + $9,000) ÷ (60 + 120 + 90)
    assert _num(r["materiales_especiales"]) == D("50")  # $500 ÷ 10 × 1


def test_la_receta_incluye_el_especial_como_una_linea_mas_y_no_suma_el_promedio(
    ejemplo: SimpleNamespace,
) -> None:
    r = ejemplo.casos["B · Receta"]
    assert _num(r["materiales_generales"]) == D(
        "150"
    )  # $2 × 10 + $20 × 4 + $50 × 1: «incluidos los especiales»
    assert _num(r["materiales_especiales"]) == D("0")  # no hay un segundo renglón de especiales
    assert _num(r["costo_total"]) == D("450")  # si sumara el promedio de la vía A daría $550


def _vista_previa(
    ejemplo: SimpleNamespace, caso: str, metodo: str, receta: list[dict[str, Any]]
) -> dict[str, Any]:
    configuracion = {
        "nombre": caso, "especialidad": "GENERAL", "duracion_clinica": 50, "espaciado": 10,
        "metodo_materiales": metodo, "importe_materiales": None, "receta": receta, "ajuste_porcentaje": "40",
    }  # fmt: skip
    return ejemplo.api(
        "POST",
        f"/tratamientos/{ejemplo.identificadores[caso]}/vista-previa",
        json={"configuracion": configuracion},
    )["resultado"]


def test_una_linea_especial_no_se_suma_en_la_receta_porque_es_de_la_via_inactiva(
    ejemplo: SimpleNamespace,
) -> None:
    """«Nunca sumes una modalidad inactiva» (reglas originales del módulo de costos)."""
    ids = ejemplo.insumos
    base = [
        {"identificador_insumo": ids["Material A"], "cantidad": "10"},
        {"identificador_insumo": ids["Material B"], "cantidad": "4"},
        {"identificador_insumo": ids["Especial"], "cantidad": "1"},
    ]
    sobrante = {"identificador_insumo": ids["Especial"], "cantidad": "5", "tipo": "INSUMO_ESPECIAL"}
    r = _vista_previa(ejemplo, "B · Receta", "RECETA_INSUMOS", [*base, sobrante])
    assert _num(r["costo_total"]) == D("450") and _num(r["materiales_especiales"]) == D("0")


def test_una_linea_general_no_se_suma_con_el_promedio_porque_es_de_la_via_inactiva(
    ejemplo: SimpleNamespace,
) -> None:
    ids = ejemplo.insumos
    especial = {"identificador_insumo": ids["Especial"], "cantidad": "1", "tipo": "INSUMO_ESPECIAL"}
    sobrante = {
        "identificador_insumo": ids["Material A"],
        "cantidad": "10",
    }  # general: de la receta B
    r = _vista_previa(
        ejemplo, "A · Promedio mensual + especial", "PROMEDIO_MENSUAL", [especial, sobrante]
    )
    assert _num(r["costo_total"]) == D("450") and _num(r["materiales_generales"]) == D("100")


def test_el_detalle_devuelve_todas_las_lineas_con_su_tipo_para_poder_reenviarlas(
    ejemplo: SimpleNamespace,
) -> None:
    """El PUT reemplaza el conjunto completo: quien edita debe recibir también las líneas de la vía inactiva."""
    a = ejemplo.api(
        "GET", f"/tratamientos/{ejemplo.identificadores['A · Promedio mensual + especial']}"
    )
    assert [(linea["nombre"], linea["tipo"]) for linea in a["receta"]] == [
        ("Especial", "INSUMO_ESPECIAL")
    ]
    b = ejemplo.api("GET", f"/tratamientos/{ejemplo.identificadores['B · Receta']}")
    assert {linea["tipo"] for linea in b["receta"]} == {"RECETA_GENERAL"} and len(b["receta"]) == 3


def test_el_importe_rapido_ignora_las_lineas_de_receta(ejemplo: SimpleNamespace) -> None:
    r = ejemplo.casos["Importe rápido"]
    assert _num(r["materiales_generales"]) == D("150") and _num(r["materiales_especiales"]) == D(
        "0"
    )


def test_un_especial_archivado_bloquea_el_calculo_en_lugar_de_omitirse(
    ejemplo: SimpleNamespace,
) -> None:
    """Un costo desconocido no equivale a un costo de cero (documento, paso 6)."""
    api = ejemplo.api
    insumo = next(
        i
        for i in api("GET", "/insumos?limite=100")["elementos"]
        if i["identificador"] == ejemplo.insumos["Especial"]
    )
    api("POST", f"/insumos/{insumo['identificador']}/archivar", rev=insumo["revision"])
    for caso in ("A · Promedio mensual + especial", "B · Receta"):
        vista = api("POST", f"/tratamientos/{ejemplo.identificadores[caso]}/vista-previa", json={})
        assert vista["estado"] == "borrador", caso
        assert "RECETA_INCOMPLETA" in {b["codigo"] for b in vista["bloqueos"]}, caso


def test_cada_respuesta_cumple_el_contrato(ejemplo: SimpleNamespace) -> None:
    assert not sorted(set(ejemplo.contrato.incumplimientos)), "\n".join(
        sorted(set(ejemplo.contrato.incumplimientos))[:20]
    )
    assert not sorted(set(ejemplo.contrato.no_documentados)), "\n".join(
        sorted(set(ejemplo.contrato.no_documentados))
    )
