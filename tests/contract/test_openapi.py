import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
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


def test_el_contrato_no_tiene_claves_duplicadas() -> None:
    """YAML se queda con la última clave repetida sin avisar; en el contrato eso esconde propiedades mal puestas."""
    import subprocess
    import sys

    resultado = subprocess.run(
        [sys.executable, "scripts/verificar_openapi.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_la_validacion_detecta_una_clave_duplicada(tmp_path: Path) -> None:
    import subprocess
    import sys

    copia = tmp_path / "docs" / "api"
    copia.mkdir(parents=True)
    original = Path("docs/api/openapi.yaml").read_text(encoding="utf-8")
    # repite la propiedad `nombre` de LineaReceta
    duplicado = original.replace(
        "        nombre:\n          type: string\n          readOnly: true\n",
        "        nombre:\n          type: string\n          readOnly: true\n        nombre:\n          type: string\n",
        1,
    )
    assert duplicado != original
    (copia / "openapi.yaml").write_text(duplicado, encoding="utf-8")
    resultado = subprocess.run(
        [sys.executable, str(Path("scripts/verificar_openapi.py").resolve())],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode != 0 and "Clave duplicada" in resultado.stderr


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
    try:
        anterior = yaml.safe_load(
            subprocess.check_output(
                ["git", "show", f"{BASE_CONTRATO}:docs/api/openapi.yaml"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        )
    except subprocess.CalledProcessError:
        pytest.skip("El commit base del contrato no está en este clon (descarga superficial o ZIP).")

    for nombre in SCHEMAS_CRITICOS:
        esquema_actual = deepcopy(actual["components"]["schemas"][nombre])
        esquema_anterior = anterior["components"]["schemas"][nombre]
        if nombre == "Sesion":
            esquema_actual["properties"].pop("modo_invitado")
            esquema_actual["required"].remove("modo_invitado")
        if nombre == "TratamientoResumen":
            # PR #6: la lista de tratamientos ahora incluye el método de materiales (cambio aditivo).
            esquema_actual["properties"].pop("metodo_materiales")
        assert esquema_actual == esquema_anterior, nombre

    sesion = actual["components"]["schemas"]["Sesion"]
    assert sesion["properties"]["modo_invitado"] == {"type": "boolean"}
    assert "modo_invitado" in sesion["required"]
