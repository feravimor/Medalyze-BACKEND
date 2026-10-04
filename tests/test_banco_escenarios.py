from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.costeo import Dinero, EntradaCosteo, Minutos, Porcentaje, calcular_costeo


def entrada(**cambios: object) -> EntradaCosteo:
    datos: dict[str, object] = {
        "gastos_fijos": Decimal("6200"),
        "gastos_variables": Decimal("1300"),
        "depreciacion": Decimal("300"),
        "dias_por_semana": 5,
        "horas_por_dia": Decimal("8"),
        "porcentaje_ocupacion": Decimal("75"),
        "duracion_clinica": 30,
        "espaciado": 10,
        "metodo_materiales": "IMPORTE_RAPIDO",
        "materiales_generales": Decimal("20"),
        "ajuste_porcentaje": Decimal("30"),
        "multiplo_redondeo": Decimal("50"),
    }
    datos.update(cambios)
    return EntradaCosteo(**datos)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("identificador", "cambios", "costo", "ajustado", "sugerido", "semaforo"),
    [
        ("B-01", {}, "60", "78", "100", "INTERMEDIO"),
        ("B-02", {"espaciado": 0}, "50", "65", "100", "ALTO"),
        ("B-03", {"porcentaje_ocupacion": Decimal("50")}, "80", "104", "150", "INTERMEDIO"),
        ("B-04", {"porcentaje_ocupacion": Decimal("100")}, "50", "65", "100", "ALTO"),
        ("B-05", {"ajuste_porcentaje": Decimal("1")}, "60", "60.6", "100", "INTERMEDIO"),
        (
            "R-01",
            {"espaciado": 0, "materiales_generales": Decimal("8"), "ajuste_porcentaje": Decimal("1")},
            "38",
            "38.38",
            "50",
            "BAJO",
        ),
        ("R-02", {"materiales_generales": Decimal("14")}, "54", "70.2", "100", "INTERMEDIO"),
        (
            "R-03",
            {"espaciado": 0, "materiales_generales": Decimal("10"), "ajuste_porcentaje": Decimal("1")},
            "40",
            "40.4",
            "50",
            "BAJO",
        ),
        (
            "L-01",
            {"espaciado": 0, "materiales_generales": Decimal("70"), "ajuste_porcentaje": Decimal("50")},
            "100",
            "150",
            "150",
            "INTERMEDIO",
        ),
        (
            "L-02",
            {"espaciado": 0, "materiales_generales": Decimal("70.01"), "ajuste_porcentaje": Decimal("50")},
            "100.01",
            "150.015",
            "200",
            "INTERMEDIO",
        ),
    ],
)
def test_escenarios_del_manual(
    identificador: str,
    cambios: dict[str, object],
    costo: str,
    ajustado: str,
    sugerido: str,
    semaforo: str,
) -> None:
    resultado = calcular_costeo(entrada(**cambios))
    assert resultado.completo, identificador
    assert resultado.costo_total == Decimal(costo), identificador
    assert resultado.importe_ajustado == Decimal(ajustado), identificador
    assert resultado.precio_sugerido == Decimal(sugerido), identificador
    assert resultado.semaforo == semaforo, identificador


def test_a03_promedio_ponderado_sin_redondeo_intermedio() -> None:
    promedio = Decimal("1000") / Decimal("7")
    resultado = calcular_costeo(
        entrada(
            espaciado=0,
            materiales_generales=promedio,
            materiales_especiales=Decimal("8"),
            ajuste_porcentaje=Decimal("1"),
        )
    )
    assert resultado.completo
    assert resultado.costo_total == Decimal("30") + promedio + Decimal("8")
    assert resultado.precio_sugerido == Decimal("200")


@given(
    materiales=st.decimals(min_value="0.01", max_value="100000", places=2),
    ajuste=st.decimals(min_value="1", max_value="500", places=2),
)
def test_precio_sugerido_es_multiplo_y_no_menor_al_ajustado(
    materiales: Decimal, ajuste: Decimal
) -> None:
    resultado = calcular_costeo(
        entrada(materiales_generales=materiales, ajuste_porcentaje=ajuste)
    )
    assert resultado.completo
    assert resultado.precio_sugerido is not None
    assert resultado.importe_ajustado is not None
    assert resultado.precio_sugerido % Decimal("50") == 0
    assert resultado.precio_sugerido >= resultado.importe_ajustado


def test_tipos_valor_rechazan_valores_invalidos() -> None:
    assert Dinero(Decimal("10.25")).valor == Decimal("10.25")
    assert Minutos(0).valor == 0
    assert Porcentaje(Decimal("500")).valor == Decimal("500")
    with pytest.raises(ValueError):
        Dinero(Decimal("NaN"))
    with pytest.raises(ValueError):
        Minutos(-1)
    with pytest.raises(ValueError):
        Porcentaje(Decimal("500.01"))
