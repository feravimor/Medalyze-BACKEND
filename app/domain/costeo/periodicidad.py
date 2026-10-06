"""Equivalente mensual exacto de un gasto según su periodicidad de pago.

Los factores se expresan como fracciones (numerador, denominador) y se aplican con ``Decimal``.
NO deben leerse de ``periodicidad_pago.factor_mensual``: esa columna guarda solo 8 decimales
(1/6 = 0.16666667, 52/12 = 4.33333333) y un gasto semestral de 46,800 daría 7,800.000156 en lugar
de 7,800, lo que puede subir un precio sugerido un múltiplo completo de redondeo (HU-08 CA1).
"""

from decimal import Decimal

FACTORES_MENSUALES: dict[str, tuple[int, int]] = {
    "SEMANAL": (52, 12),
    "QUINCENAL": (2, 1),
    "MENSUAL": (1, 1),
    "BIMESTRAL": (1, 2),
    "TRIMESTRAL": (1, 3),
    "SEMESTRAL": (1, 6),
    "ANUAL": (1, 12),
}


def equivalente_mensual(importe: Decimal, codigo_periodicidad: str) -> Decimal:
    """Importe pagado en la periodicidad indicada, expresado por mes (multiplica y luego divide)."""
    try:
        numerador, denominador = FACTORES_MENSUALES[codigo_periodicidad]
    except KeyError as exc:
        raise ValueError(f"Periodicidad desconocida: {codigo_periodicidad!r}") from exc
    return importe * Decimal(numerador) / Decimal(denominador)
