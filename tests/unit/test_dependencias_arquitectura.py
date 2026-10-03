import ast
from pathlib import Path


def test_dominio_no_importa_frameworks() -> None:
    prohibidos = {"fastapi", "sqlalchemy", "pydantic", "asyncpg"}
    violaciones = []
    for archivo in Path("app/domain").rglob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                modulos = {alias.name.split(".")[0] for alias in nodo.names}
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                modulos = {nodo.module.split(".")[0]}
            else:
                continue
            if modulos & prohibidos:
                violaciones.append(f"{archivo}: {sorted(modulos & prohibidos)}")
    assert not violaciones, violaciones
