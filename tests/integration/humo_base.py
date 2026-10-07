"""Armazón de la prueba de humo: cliente HTTP, verificación contra el contrato OpenAPI y
registro de cobertura de operaciones.

No contiene pruebas. Lo usa ``test_prueba_de_humo.py``.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

RAIZ = Path(__file__).resolve().parents[2]
METODOS = ("get", "post", "put", "patch", "delete")
PREFIJO = "/api/v1"


def _descripcion(error: Any) -> str:
    """Describe una diferencia con el contrato sin valores variables, para poder compararla entre corridas."""
    ruta = "/".join("*" if isinstance(p, int) else str(p) for p in error.absolute_path) or "(raíz)"
    if error.validator == "required":
        nombre = re.search(r"'([^']+)' is a required property", error.message)
        detalle = f"falta el campo «{nombre.group(1) if nombre else '?'}»"
    elif error.validator == "additionalProperties":
        detalle = "campos no documentados: " + ", ".join(sorted(re.findall(r"'([^']+)'", error.message.split("(")[-1])))
    elif error.validator == "type":
        detalle = f"se esperaba {error.validator_value} y llegó {type(error.instance).__name__}"
    elif error.validator == "pattern":
        detalle = f"no cumple el patrón {error.validator_value}"
    elif error.validator in ("oneOf", "anyOf"):
        detalle = "no coincide con ninguna de las formas documentadas"
    else:
        detalle = f"{error.validator} {str(error.validator_value)[:70]}"
    return f"{ruta}: {detalle}"


class Contrato:
    """Lee ``docs/api/openapi.yaml`` y verifica respuestas contra él."""

    def __init__(self) -> None:
        self.doc: dict[str, Any] = yaml.safe_load(
            (RAIZ / "docs/api/openapi.yaml").read_text(encoding="utf-8")
        )
        self.operaciones: set[tuple[str, str]] = {
            (metodo.upper(), plantilla)
            for plantilla, item in self.doc["paths"].items()
            for metodo in item
            if metodo in METODOS
        }
        # Las rutas con menos parámetros van primero: /tratamientos/importar-plantillas
        # debe resolverse antes que /tratamientos/{identificador}.
        self._patrones = sorted(
            (
                (re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", plantilla) + "$"), plantilla)
                for plantilla in self.doc["paths"]
            ),
            key=lambda par: par[1].count("{"),
        )
        self.exitosas: set[tuple[str, str]] = set()
        self.incumplimientos: list[str] = []
        self.no_documentados: list[str] = []

    def plantilla(self, ruta: str) -> str | None:
        ruta = ruta.split("?")[0]
        for patron, plantilla in self._patrones:
            if patron.match(ruta):
                return plantilla
        return None

    def registrar(self, metodo: str, ruta: str, estado: int, cuerpo: Any) -> None:
        plantilla = self.plantilla(ruta)
        if plantilla is None:
            self.incumplimientos.append(f"{metodo} {ruta}: la ruta no existe en el contrato")
            return
        if 200 <= estado < 300:
            self.exitosas.add((metodo.upper(), plantilla))
        self._verificar(metodo, plantilla, estado, cuerpo)

    def _verificar(self, metodo: str, plantilla: str, estado: int, cuerpo: Any) -> None:
        operacion = self.doc["paths"][plantilla].get(metodo.lower())
        if operacion is None:
            self.incumplimientos.append(f"{metodo} {plantilla}: el método no está en el contrato")
            return
        respuesta = operacion["responses"].get(str(estado)) or operacion["responses"].get("default")
        if respuesta is None:
            self.no_documentados.append(f"{metodo} {plantilla} devolvió {estado}, no documentado")
            return
        contenido = respuesta.get("content", {}).get("application/json")
        if contenido is None:
            if cuerpo not in (None, "", {}):
                self.incumplimientos.append(
                    f"{metodo} {plantilla} → {estado}: el contrato no define cuerpo y se recibió uno"
                )
            return
        validador = Draft202012Validator(
            {"components": self.doc["components"], "allOf": [contenido["schema"]]},
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        for error in validador.iter_errors(cuerpo):
            self.incumplimientos.append(f"{metodo} {plantilla} → {estado} · {_descripcion(error)}")

    def sin_ejercitar(self) -> list[str]:
        return sorted(f"{m} {p}" for m, p in self.operaciones - self.exitosas)


class Api:
    """Cliente con la sesión de un usuario; cada llamada se registra y se verifica."""

    def __init__(self, cliente: TestClient, contrato: Contrato, token: str | None = None) -> None:
        self.cliente = cliente
        self.contrato = contrato
        self.token = token

    def __call__(
        self,
        metodo: str,
        ruta: str,
        *,
        json: Any = None,
        rev: int | str | None = None,
        clave: str | None = None,
        sesion: bool = True,
        estado: int | None = None,
        encabezados: dict[str, str] | None = None,
    ) -> Any:
        cabeceras = dict(encabezados or {})
        if sesion and self.token:
            cabeceras["Authorization"] = f"Bearer {self.token}"
        if rev is not None:
            cabeceras["If-Match"] = str(rev)
        if clave is not None:
            cabeceras["Idempotency-Key"] = clave
        respuesta = self.cliente.request(metodo, PREFIJO + ruta, json=json, headers=cabeceras)
        try:
            cuerpo = respuesta.json() if respuesta.content else None
        except ValueError:
            cuerpo = respuesta.text
        self.contrato.registrar(metodo, ruta, respuesta.status_code, cuerpo)
        if estado is not None:
            assert respuesta.status_code == estado, (
                f"{metodo} {ruta} devolvió {respuesta.status_code} y se esperaba {estado}: "
                f"{respuesta.text[:300]}"
            )
        return respuesta


def clave_nueva() -> str:
    return f"humo-{uuid.uuid4().hex}"


def buscar(cuerpo: Any, nombre: str) -> Any:
    """Busca un campo por nombre en el nivel superior o en cualquier objeto anidado."""
    if isinstance(cuerpo, dict):
        if nombre in cuerpo:
            return cuerpo[nombre]
        for valor in cuerpo.values():
            encontrado = buscar(valor, nombre)
            if encontrado is not None:
                return encontrado
    return None
