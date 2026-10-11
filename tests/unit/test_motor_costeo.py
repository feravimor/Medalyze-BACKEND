from decimal import Decimal

from app.domain.costeo import EntradaCosteo, calcular_costeo


def caso_base(**cambios):
    datos = dict(
        gastos_fijos=Decimal("6200"),
        gastos_variables=Decimal("1300"),
        depreciacion=Decimal("300"),
        dias_por_semana=5,
        horas_por_dia=Decimal("8"),
        porcentaje_ocupacion=Decimal("75"),
        duracion_clinica=30,
        espaciado=10,
        metodo_materiales="IMPORTE_RAPIDO",
        materiales_generales=Decimal("20"),
        ajuste_porcentaje=Decimal("30"),
        multiplo_redondeo=Decimal("50"),
    )
    datos.update(cambios)
    return EntradaCosteo(**datos)


def test_mat_01_coincide_con_manual() -> None:
    resultado = calcular_costeo(caso_base())
    assert resultado.completo
    assert resultado.pool_mensual == Decimal("7800")
    assert resultado.minutos_disponibles == 10400
    assert resultado.minutos_efectivos == 7800
    assert resultado.costo_por_minuto == Decimal("1")
    assert resultado.costo_tiempo == Decimal("40")
    assert resultado.costo_total == Decimal("60")
    assert resultado.importe_ajustado == Decimal("78.0")
    assert resultado.precio_sugerido == Decimal("100")
    assert resultado.margen_porcentaje == Decimal("40.0")
    assert resultado.semaforo == "INTERMEDIO"


def test_ocupacion_cero_bloquea_sin_dividir() -> None:
    resultado = calcular_costeo(caso_base(porcentaje_ocupacion=Decimal("0")))
    assert not resultado.completo
    assert any(b.codigo.value == "SIN_TIEMPO_ATENCION" for b in resultado.bloqueos)
    assert resultado.costo_por_minuto is None


def test_importe_rapido_debe_ser_mayor_a_cero() -> None:
    resultado = calcular_costeo(caso_base(materiales_generales=Decimal("0")))
    assert not resultado.completo
    assert any(b.codigo.value == "IMPORTE_MATERIALES_FALTANTE" for b in resultado.bloqueos)


def test_espaciado_cero_se_conserva() -> None:
    resultado = calcular_costeo(caso_base(espaciado=0))
    assert resultado.completo
    assert resultado.minutos_imputados == 30


def test_espaciado_nulo_bloquea_sin_predeterminado() -> None:
    resultado = calcular_costeo(caso_base(espaciado=None))
    assert not resultado.completo
    assert any(
        b.codigo.value == "SIN_ESPACIADO_PREDETERMINADO" for b in resultado.bloqueos
    )
