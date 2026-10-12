"""Ejecuta el EJEMPLO NUMÉRICO OFICIAL por las tres vías de materiales a través de la API.

Fuente: ``Medalyze_Recorrido_Completo_Ejemplo_Numerico.pdf`` (09 oct 2026): de $26,000 de costo operativo
mensual hasta un precio sugerido de $650 y un margen de 30.77 %, por la vía A (promedio mensual más un
material especial), la B (receta) y el importe rápido.

Uso (con la API corriendo; crea una cuenta nueva en cada ejecución):
    python scripts/ejemplo_oficial.py
    python scripts/ejemplo_oficial.py --url http://127.0.0.1:8000/api/v1

Termina con código 1 si algún valor no coincide con el documento. Reutiliza el cliente HTTP de
``scripts/datos_demo.py`` (debe estar en la misma carpeta).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

Llamar = Callable[..., tuple[int, Any]]

CONTRASENA = "Demo-Medalyze-2026"

# --- Los datos del documento ---------------------------------------------------------------------
GASTOS = [  # nombre, categoría, importe capturado, periodicidad  → $20,000 fijos y $4,000 variables al mes
    ("Renta", "FIJO", "12000", "MENSUAL"),
    ("Asistente", "FIJO", "3500", "QUINCENAL"),
    ("Software", "FIJO", "12000", "ANUAL"),
    ("Electricidad", "VARIABLE", "3600", "BIMESTRAL"),
    ("Agua", "VARIABLE", "300", "MENSUAL"),
    ("Servicio de limpieza", "VARIABLE", "1200", "MENSUAL"),
    ("Mantenimiento", "VARIABLE", "8400", "ANUAL"),
]
INSUMOS = [  # nombre, presentación, unidad, contenido, precio
    ("Material A", "Caja", "PZA", "100", "200"),  # $2 por pieza
    ("Material B", "Frasco", "ML", "20", "400"),  # $20 por mL
    ("Especial", "Caja", "PZA", "10", "500"),  # $50 por pieza
]
MESES = [("2026-07-01", "6000", 60), ("2026-08-01", "12000", 120), ("2026-09-01", "9000", 90)]

# --- Lo que dice el documento -----------------------------------------------------------------------
D = Decimal
ESPERADO: dict[str, Any] = {
    "total_mensual": D("26000"),
    "minutos_disponibles": 10400,
    "minutos_efectivos": 5200,
    "costo_por_minuto": D("5"),
    "costo_tiempo": D("300"),
    "materiales": D("150"),  # generales + especiales, por cualquiera de las tres vías
    "costo_total": D("450"),
    "importe_ajustado": D("630"),  # $450 × 1.40
    "precio_sugerido": D("650"),
    "margen_porcentaje": D("30.77"),
}
CASOS = ("A · Promedio mensual + especial", "B · Receta", "Importe rápido")


def _cliente_http() -> Any:
    ruta = Path(__file__).with_name("datos_demo.py")
    especificacion = importlib.util.spec_from_file_location("datos_demo", ruta)
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def ejecutar(llamar: Llamar) -> dict[str, Any]:
    """Crea una cuenta con los datos del documento, calcula las tres vías y devuelve lo obtenido."""
    api = _cliente_http()._Api(llamar)
    correo = f"oficial-{os.urandom(3).hex()}@ejemplo.mx"
    estado, cuerpo = llamar(
        "POST", "/autenticacion/registro", json={"nombre_completo": "Dra. Ejemplo", "correo": correo,
        "contrasena": CONTRASENA, "nombre_consultorio": "Ejemplo oficial"}, rev=None, clave=None, token=None,
    )  # fmt: skip
    if estado != 201:
        raise RuntimeError(f"No se pudo crear la cuenta: {estado} {cuerpo}")
    api.token = cuerpo["token_acceso"]

    for nombre, categoria, importe, periodicidad in GASTOS:
        api("POST", "/gastos", json={"nombre": nombre, "categoria": categoria, "importe_pagado_por_periodo": importe,
                                      "codigo_periodicidad": periodicidad, "fecha_inicio_vigencia": "2026-01-01", "activo": True})  # fmt: skip
    api("POST", "/equipos", json={"nombre": "Equipo", "precio_adquisicion": "120000", "valor_residual": "0",
                                   "vida_util_anios": 5, "fecha_alta_en_servicio": "2026-01-01", "estado": "ACTIVO"})  # fmt: skip
    api("PUT", "/perfil-capacidad", rev=0, json={"dias_por_semana": 5, "horas_por_dia": "8",
                                                  "porcentaje_ocupacion": "50", "ocupacion_confirmada": True})  # fmt: skip
    ids = {}
    for nombre, presentacion, unidad, contenido, precio in INSUMOS:
        ids[nombre] = api("POST", "/insumos", json={"nombre": nombre, "presentacion": presentacion,
                                                     "codigo_unidad": unidad, "cantidad_contenida": contenido,
                                                     "precio_presentacion": precio})["identificador"]  # fmt: skip
    for mes, consumo, atendidos in MESES:
        api("POST", "/periodos-mensuales", json={"mes": mes, "consumo_materiales": consumo,
                                                  "tratamientos_atendidos": atendidos, "procedencia": "PERIODO_ANTERIOR", "notas": None})  # fmt: skip

    especial = {
        "identificador_insumo": ids["Especial"],
        "cantidad": "1",
        "merma_porcentaje": "0",
        "tipo": "INSUMO_ESPECIAL",
    }
    # En la receta B el material especial es una línea más de la receta (el documento: «incluidos los especiales»).
    especial_en_receta = {
        "identificador_insumo": ids["Especial"],
        "cantidad": "1",
        "merma_porcentaje": "0",
    }
    configuraciones: dict[str, dict[str, Any]] = {
        CASOS[0]: {"metodo": "PROMEDIO_MENSUAL", "importe": None, "receta": [especial]},
        CASOS[1]: {"metodo": "RECETA_INSUMOS", "importe": None, "receta": [
            {"identificador_insumo": ids["Material A"], "cantidad": "10", "merma_porcentaje": "0"},
            {"identificador_insumo": ids["Material B"], "cantidad": "4", "merma_porcentaje": "0"}, especial_en_receta]},
        CASOS[2]: {"metodo": "IMPORTE_RAPIDO", "importe": "150", "receta": []},
    }  # fmt: skip
    resultados: dict[str, Any] = {}
    identificadores: dict[str, str] = {}
    for nombre, c in configuraciones.items():
        t = api("POST", "/tratamientos", clave=f"of-{os.urandom(8).hex()}",
                json={"nombre": nombre, "especialidad": "GENERAL", "duracion_clinica": 50})  # fmt: skip
        detalle = api("PUT", f"/tratamientos/{t['identificador']}/configuracion", rev=t["revision"], json={
            "nombre": nombre, "especialidad": "GENERAL", "duracion_clinica": 50, "espaciado": 10,
            "metodo_materiales": c["metodo"], "importe_materiales": c["importe"], "receta": c["receta"],
            "ajuste_porcentaje": "40"})  # fmt: skip
        api("POST", f"/tratamientos/{t['identificador']}/calculos", clave=f"of-{os.urandom(8).hex()}",
            json={"revision_tratamiento": detalle["revision"]}, rev=detalle["revision"])  # fmt: skip
        resultados[nombre] = api("GET", f"/tratamientos/{t['identificador']}")["ultimo_resultado"]
        identificadores[nombre] = t["identificador"]
    return {
        "costos": api("GET", "/costos-indirectos/resumen"),
        "casos": resultados,
        "identificadores": identificadores,
        "insumos": ids,
        "api": api,
    }


def _filas(obtenido: dict[str, Any]) -> list[tuple[str, str, Any, Any]]:
    """(sección, concepto, obtenido, esperado) para imprimir y comparar."""
    costos = obtenido["costos"]
    filas: list[tuple[str, str, Any, Any]] = [
        ("", "Costo operativo mensual", costos["total_mensual"], ESPERADO["total_mensual"]),
        ("", "Minutos disponibles", costos["minutos_disponibles"], ESPERADO["minutos_disponibles"]),
        ("", "Minutos de atención", costos["minutos_efectivos"], ESPERADO["minutos_efectivos"]),
        ("", "Costo por minuto", costos["costo_por_minuto"], ESPERADO["costo_por_minuto"]),
    ]
    for nombre, r in obtenido["casos"].items():
        materiales = D(str(r["materiales_generales"])) + D(str(r["materiales_especiales"]))
        filas += [
            (nombre, "Costo de tiempo", r["costo_tiempo"], ESPERADO["costo_tiempo"]),
            (nombre, "Materiales (generales + especiales)", materiales, ESPERADO["materiales"]),
            (nombre, "Costo base", r["costo_total"], ESPERADO["costo_total"]),
            (
                nombre,
                "Precio antes de redondear",
                r["importe_ajustado"],
                ESPERADO["importe_ajustado"],
            ),
            (nombre, "Precio sugerido", r["precio_sugerido"], ESPERADO["precio_sugerido"]),
            (nombre, "Margen estimado %", r["margen_porcentaje"], ESPERADO["margen_porcentaje"]),
        ]
    return filas


def coincide(obtenido: Any, esperado: Any) -> bool:
    if isinstance(esperado, int) and not isinstance(esperado, bool):
        return int(obtenido) == esperado
    return D(str(obtenido)).quantize(D("0.01")) == D(str(esperado)).quantize(D("0.01"))


def main() -> int:
    analizador = argparse.ArgumentParser(
        description="Ejecuta el ejemplo numérico oficial contra la API."
    )
    analizador.add_argument(
        "--url", default=os.getenv("MEDALYZE_API_URL", "http://127.0.0.1:8000/api/v1")
    )
    url = analizador.parse_args().url.rstrip("/")
    try:
        obtenido = ejecutar(_cliente_http()._transporte_http(url))
    except Exception as error:  # noqa: BLE001 - se informa y se sale con código 1
        print(f"No se pudo ejecutar el ejemplo: {error}", file=sys.stderr)
        return 1
    todo = True
    seccion = None
    print(f"{'':<38}{'obtenido':>12}{'esperado':>12}")
    for nombre, concepto, valor, esperado in _filas(obtenido):
        if nombre != seccion:
            print(f"\n--- {nombre}" if nombre else "")
            seccion = nombre
        ok = coincide(valor, esperado)
        todo = todo and ok
        mostrar = f"{D(str(valor)):.2f}" if not isinstance(esperado, int) else str(valor)
        print(f"{concepto:<38}{mostrar:>12}{esperado!s:>12}   {'✓' if ok else '✗ DIFERENTE'}")
    print(
        "\nRESULTADO:",
        "TODO COINCIDE CON EL DOCUMENTO" if todo else "HAY DIFERENCIAS CON EL DOCUMENTO",
    )
    return 0 if todo else 1


if __name__ == "__main__":
    sys.exit(main())
