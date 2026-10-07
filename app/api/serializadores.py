"""Arma las respuestas de la hoja de costos con la forma que documenta ``docs/api/openapi.yaml``.

La base de datos guarda la hoja en columnas planas; el contrato la describe como un objeto
estructurado (``resultado``, ``datos_aplicados``, ``lineas_insumo``…). Este módulo hace esa traducción
en un solo lugar para que el cálculo, el historial, el detalle y el inicio respondan igual.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.application.utilidades import limpiar_json

_DIEZ_DECIMALES = Decimal("0.0000000001")
_CUATRO_DECIMALES = Decimal("0.0001")


def texto_decimal(valor: Any) -> str:
    """Decimal como texto con a lo más 10 decimales (el patrón que exige el contrato)."""
    # format(..., "f"): str(Decimal("0E-10")) saldría en notación científica y no cumpliría el patrón.
    return format(Decimal(valor).quantize(_DIEZ_DECIMALES, rounding=ROUND_HALF_UP), "f")


def porcentaje(valor: Any) -> float:
    return float(Decimal(valor).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP))


def resultado_costo(fila: Any) -> dict[str, Any]:
    """``ResultadoCosto``: los nueve campos que el contrato exige, desde una hoja o un cálculo."""
    return {
        "costo_tiempo": texto_decimal(fila["costo_tiempo"]),
        "materiales_generales": texto_decimal(fila["materiales_generales"]),
        "materiales_especiales": texto_decimal(fila["materiales_especiales"]),
        "costo_total": texto_decimal(fila["costo_total"]),
        "ajuste_porcentaje": porcentaje(fila["ajuste_porcentaje"]),
        "importe_ajustado": texto_decimal(fila["importe_ajustado"]),
        "precio_sugerido": texto_decimal(fila["precio_sugerido"]),
        "margen_porcentaje": porcentaje(fila["margen_porcentaje"]),
        "semaforo": str(fila["semaforo"]),
    }


def hoja_resumen(fila: Any, metodo_materiales: str | None, vigente: bool) -> dict[str, Any]:
    """``HojaCostosResumen``: lo que muestran el historial y el inicio."""
    return {
        "identificador": str(fila["identificador"]),
        "fecha_creacion": fila["fecha_hora_creacion"].isoformat(),
        "resultado": resultado_costo(fila),
        "metodo_materiales": metodo_materiales or "",
        "vigente": bool(vigente),
    }


def hoja_completa(
    fila: Any,
    metodo_materiales: str | None,
    lineas: list[Any],
    periodos: list[Any],
    aportes: list[Any],
) -> dict[str, Any]:
    """``HojaCostos``: el detalle inmutable de un cálculo."""
    return limpiar_json(
        {
            "identificador": fila["identificador"],
            "identificador_tratamiento": fila["identificador_tratamiento"],
            "fecha_creacion": fila["fecha_hora_creacion"],
            "datos_aplicados": {
                "gastos_fijos": texto_decimal(fila["gastos_fijos"]),
                "gastos_variables": texto_decimal(fila["gastos_variables"]),
                "depreciacion": texto_decimal(fila["depreciacion"]),
                "pool_mensual": texto_decimal(fila["pool_mensual"]),
                "metodo_materiales": metodo_materiales,
                "madurez_base": str(fila["madurez"]) if fila["madurez"] else None,
            },
            "aportes": [dict(a) for a in aportes],
            "minutos_disponibles": fila["minutos_disponibles"],
            "minutos_efectivos": fila["minutos_efectivos"],
            "costo_por_minuto": texto_decimal(fila["costo_por_minuto"]),
            "minutos_imputados": fila["minutos_imputados"],
            "lineas_insumo": [dict(x) for x in lineas],
            "periodos": [dict(x) for x in periodos],
            "resultado": resultado_costo(fila),
            "version_formula": fila["version_formula"],
            "sustituye_a": fila["sustituye_a"],
        }
    )
