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
