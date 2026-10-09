from decimal import Decimal
from fractions import Fraction

import pytest

from app.domain.costeo.periodicidad import FACTORES_MENSUALES, equivalente_mensual


@pytest.mark.parametrize(
    ("codigo", "importe", "esperado"),
    [
        ("SEMANAL", "300", "1300"),  # HU-08 CA1: no 1,299.99
        ("QUINCENAL", "100", "200"),
        ("MENSUAL", "7800", "7800"),
        ("BIMESTRAL", "1800", "900"),
        ("TRIMESTRAL", "900", "300"),
        ("SEMESTRAL", "1200", "200"),
        ("ANUAL", "2400", "200"),
    ],
)
def test_las_siete_periodicidades_son_exactas(codigo: str, importe: str, esperado: str) -> None:
    assert equivalente_mensual(Decimal(importe), codigo) == Decimal(esperado)


def test_un_gasto_semestral_de_46800_es_exactamente_7800() -> None:
    # Con el factor redondeado de la base (0.16666667) daba 7,800.000156.
    assert equivalente_mensual(Decimal("46800"), "SEMESTRAL") == Decimal("7800")


@pytest.mark.parametrize("codigo", sorted(FACTORES_MENSUALES))
def test_coincide_con_la_aritmetica_fraccionaria_exacta(codigo: str) -> None:
    numerador, denominador = FACTORES_MENSUALES[codigo]
    for importe in ("1", "37.50", "1234.56", "99999.99"):
        exacto = Fraction(importe) * Fraction(numerador, denominador)
        calculado = equivalente_mensual(Decimal(importe), codigo)
        assert abs(Fraction(calculado) - exacto) < Fraction(1, 10**20)


def test_periodicidad_desconocida_falla_con_claridad() -> None:
    with pytest.raises(ValueError, match="desconocida"):
        equivalente_mensual(Decimal("1"), "DECENAL")
