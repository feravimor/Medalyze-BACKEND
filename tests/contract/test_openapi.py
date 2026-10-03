from pathlib import Path

import yaml

from app.main import app

VERBOS_HTTP = {"get", "post", "put", "patch", "delete"}


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
