"""Reglas del motor sobre los materiales especiales (documento: «Del tiempo a los materiales»)."""

from decimal import Decimal

from app.domain.costeo.bloqueos import CodigoBloqueo
from app.domain.costeo.motor import EntradaCosteo, calcular_costeo

D = Decimal


def _entrada(**cambios: object) -> EntradaCosteo:
    base: dict[str, object] = {
        "gastos_fijos": D("20000"), "gastos_variables": D("4000"), "depreciacion": D("2000"),
        "dias_por_semana": 5, "horas_por_dia": D("8"), "porcentaje_ocupacion": D("50"),
        "duracion_clinica": 50, "espaciado": 10, "metodo_materiales": "PROMEDIO_MENSUAL",
        "materiales_generales": D("100"), "materiales_especiales": D("50"),
        "ajuste_porcentaje": D("40"), "multiplo_redondeo": D("50"),
    }  # fmt: skip
    base.update(cambios)
    return EntradaCosteo(**base)  # type: ignore[arg-type]


def _codigos(entrada: EntradaCosteo) -> set[CodigoBloqueo]:
    return {b.codigo for b in calcular_costeo(entrada).bloqueos}


def test_el_promedio_mas_el_especial_da_el_precio_del_documento() -> None:
    r = calcular_costeo(_entrada())
    assert r.completo and r.costo_total == D("450") and r.precio_sugerido == D("650")
    assert round(r.margen_porcentaje or D(0), 2) == D("30.77")


def test_un_especial_desconocido_con_el_promedio_bloquea() -> None:
    assert _codigos(_entrada(materiales_especiales=None)) == {CodigoBloqueo.RECETA_INCOMPLETA}


def test_el_promedio_en_cero_con_especiales_sigue_bloqueado() -> None:
    """Los materiales generales deben ser mayores que cero por sí solos: el específico no los sustituye."""
    entrada = _entrada(materiales_generales=D("0"), materiales_especiales=D("50"))
    assert _codigos(entrada) == {CodigoBloqueo.MATERIALES_EN_CERO}


def test_una_receta_sin_nada_que_costear_sigue_bloqueada() -> None:
    entrada = _entrada(
        metodo_materiales="RECETA_INSUMOS",
        materiales_generales=D("0"),
        materiales_especiales=D("0"),
    )
    assert _codigos(entrada) == {CodigoBloqueo.RECETA_INCOMPLETA}


def test_una_receta_con_un_insumo_archivado_sigue_bloqueada() -> None:
    entrada = _entrada(
        metodo_materiales="RECETA_INSUMOS", materiales_generales=None, materiales_especiales=None
    )
    assert _codigos(entrada) == {CodigoBloqueo.RECETA_INCOMPLETA}


def test_el_importe_rapido_no_cambia() -> None:
    r = calcular_costeo(
        _entrada(
            metodo_materiales="IMPORTE_RAPIDO",
            materiales_generales=D("150"),
            materiales_especiales=D("0"),
        )
    )
    assert r.completo and r.costo_total == D("450")
