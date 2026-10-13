import subprocess
from copy import deepcopy
from pathlib import Path

import yaml

from app.main import app

VERBOS_HTTP = {"get", "post", "put", "patch", "delete"}
RUTAS_DEMO = {
    "/demo/escenarios": ("get", "ListaEscenariosDemo"),
    "/demo/sesiones": ("post", "SesionDemo"),
    "/demo/sesiones/actual": ("delete", None),
}
BASE_CONTRATO = "836765bb2191f4ff9c0d670eea7c8dbd7aee715c"
SCHEMAS_CRITICOS = (
    "TratamientoResumen",
    "ResumenCostosIndirectos",
    "PeriodoMensual",
    "PeriodoMensualEntrada",
    "Organizacion",
    "PerfilCapacidad",
    "Sesion",
    "EstadoAvisoPrivacidad",
)


def test_contrato_contiene_operaciones_del_ticket() -> None:
    contrato = yaml.safe_load(Path("docs/api/openapi.yaml").read_text(encoding="utf-8"))
    assert contrato["openapi"] == "3.1.0"
    assert "/autenticacion/registro" in contrato["paths"]
    assert "/tratamientos/{identificador}/calculos" in contrato["paths"]
    assert "/inicio/resumen" in contrato["paths"]
    assert "BearerJWT" in contrato["components"]["securitySchemes"]


def test_implementacion_cubre_todas_las_operaciones_del_contrato() -> None:
    contrato = yaml.safe_load(Path("docs/api/openapi.yaml").read_text(encoding="utf-8"))
    documentacion_generada = app.openapi()

    operaciones_contrato = {
        (ruta, metodo)
        for ruta, definicion in contrato["paths"].items()
        for metodo in definicion
        if metodo in VERBOS_HTTP
    }
    operaciones_implementadas = {
        (ruta.removeprefix("/api/v1"), metodo)
        for ruta, definicion in documentacion_generada["paths"].items()
        for metodo in definicion
        if metodo in VERBOS_HTTP
    }

    assert operaciones_implementadas == operaciones_contrato


def test_contrato_demo_esta_tipado_y_coincide_con_fastapi() -> None:
    contrato = yaml.safe_load(Path("docs/api/openapi.yaml").read_text(encoding="utf-8"))
    generado = app.openapi()

    for ruta, (metodo, respuesta) in RUTAS_DEMO.items():
        operacion_estatica = contrato["paths"][ruta][metodo]
        operacion_generada = generado["paths"][f"/api/v1{ruta}"][metodo]
        if respuesta is None:
            assert "content" not in operacion_estatica["responses"]["204"]
            assert "content" not in operacion_generada["responses"]["204"]
            continue
        estado = "200" if metodo == "get" else "201"
        ref_estatica = operacion_estatica["responses"][estado]["content"]["application/json"][
            "schema"
        ]["$ref"]
        ref_generada = operacion_generada["responses"][estado]["content"]["application/json"][
            "schema"
        ]["$ref"]
        assert ref_estatica == ref_generada == f"#/components/schemas/{respuesta}"

    request_estatico = contrato["paths"]["/demo/sesiones"]["post"]["requestBody"]
    request_generado = generado["paths"]["/api/v1/demo/sesiones"]["post"]["requestBody"]
    assert request_estatico["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/CrearDemoEntrada"
    )
    assert request_generado["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/CrearDemoEntrada"
    )

    for nombre in ("EscenarioDemo", "ListaEscenariosDemo", "CrearDemoEntrada", "SesionDemo"):
        estatico = contrato["components"]["schemas"][nombre]
        runtime = generado["components"]["schemas"][nombre]
        assert estatico["additionalProperties"] is False
        assert runtime["additionalProperties"] is False
        assert set(estatico["properties"]) == set(runtime["properties"])
        assert set(estatico["required"]) == set(runtime["required"])

    assert contrato["paths"]["/demo/sesiones/actual"]["delete"]["security"] == [
        {"BearerJWT": []}
    ]
    assert {"BearerJWT": []} in generado["paths"]["/api/v1/demo/sesiones/actual"]["delete"][
        "security"
    ]


def test_delete_demo_referencia_el_esquema_de_seguridad_real() -> None:
    contrato = yaml.safe_load(Path("docs/api/openapi.yaml").read_text(encoding="utf-8"))
    generado = app.openapi()

    assert contrato["paths"]["/demo/sesiones/actual"]["delete"]["security"] == [
        {"BearerJWT": []}
    ]
    seguridad_runtime = generado["paths"]["/api/v1/demo/sesiones/actual"]["delete"]["security"]
    assert {"BearerJWT": []} in seguridad_runtime
    esquema_inexistente = "bearer" + "Auth"
    assert esquema_inexistente not in str(contrato)
    assert esquema_inexistente not in str(generado)


def test_contrato_critico_conserva_compatibilidad_pre_demo() -> None:
    actual = yaml.safe_load(Path("docs/api/openapi.yaml").read_text(encoding="utf-8"))
    anterior = yaml.safe_load(
        subprocess.check_output(
            ["git", "show", f"{BASE_CONTRATO}:docs/api/openapi.yaml"], text=True
        )
    )

    for nombre in SCHEMAS_CRITICOS:
        esquema_actual = deepcopy(actual["components"]["schemas"][nombre])
        esquema_anterior = anterior["components"]["schemas"][nombre]
        if nombre == "Sesion":
            esquema_actual["properties"].pop("modo_invitado")
            esquema_actual["required"].remove("modo_invitado")
        assert esquema_actual == esquema_anterior, nombre

    sesion = actual["components"]["schemas"]["Sesion"]
    assert sesion["properties"]["modo_invitado"] == {"type": "boolean"}
    assert "modo_invitado" in sesion["required"]
