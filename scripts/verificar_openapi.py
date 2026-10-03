import re
import sys
from pathlib import Path
from typing import Any

import yaml

documento = yaml.safe_load(Path("docs/api/openapi.yaml").read_text(encoding="utf-8"))
errores: list[str] = []
ids: set[str] = set()


def recorrer(valor: Any, ruta: str = "$") -> None:
    if isinstance(valor, dict):
        for clave, contenido in valor.items():
            if clave == "$ref" and contenido.startswith("#/"):
                actual = documento
                for parte in contenido[2:].split("/"):
                    if parte not in actual:
                        errores.append(f"Referencia rota en {ruta}: {contenido}")
                        break
                    actual = actual[parte]
            else:
                recorrer(contenido, f"{ruta}.{clave}")
    elif isinstance(valor, list):
        for indice, contenido in enumerate(valor):
            recorrer(contenido, f"{ruta}[{indice}]")


recorrer(documento)
for ruta, item in documento["paths"].items():
    esperados = set(re.findall(r"{([^}]+)}", ruta))
    for metodo, operacion in item.items():
        operation_id = operacion.get("operationId")
        if not operation_id or operation_id in ids:
            errores.append(f"operationId ausente o duplicado: {metodo} {ruta}")
        ids.add(operation_id)
        encontrados: set[str] = set()
        for parametro in operacion.get("parameters", []):
            if "$ref" in parametro:
                parametro = documento["components"]["parameters"][
                    parametro["$ref"].rsplit("/", 1)[-1]
                ]
            if parametro.get("in") == "path":
                encontrados.add(parametro["name"])
        if esperados != encontrados:
            errores.append(f"Parámetros incompatibles: {metodo} {ruta}")

if errores:
    print("\n".join(errores))
    sys.exit(1)
print(f"OpenAPI válido estructuralmente: {len(documento['paths'])} rutas, {len(ids)} operaciones")
