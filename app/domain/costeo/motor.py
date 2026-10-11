from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from app.domain.costeo.bloqueos import Bloqueo, CodigoBloqueo

CERO = Decimal("0")
CIEN = Decimal("100")


@dataclass(frozen=True, slots=True)
class EntradaCosteo:
    gastos_fijos: Decimal
    gastos_variables: Decimal
    depreciacion: Decimal
    dias_por_semana: int | None
    horas_por_dia: Decimal | None
    porcentaje_ocupacion: Decimal | None
    duracion_clinica: int
    espaciado: int | None
    metodo_materiales: str | None
    materiales_generales: Decimal | None
    materiales_especiales: Decimal = CERO
    ajuste_porcentaje: Decimal = Decimal("1")
    multiplo_redondeo: Decimal = Decimal("50")


@dataclass(frozen=True, slots=True)
class ResultadoCosteo:
    completo: bool
    bloqueos: tuple[Bloqueo, ...] = field(default_factory=tuple)
    pool_mensual: Decimal | None = None
    minutos_disponibles: int | None = None
    minutos_efectivos: int | None = None
    costo_por_minuto: Decimal | None = None
    minutos_imputados: int | None = None
    costo_tiempo: Decimal | None = None
    materiales_generales: Decimal | None = None
    materiales_especiales: Decimal | None = None
    costo_total: Decimal | None = None
    importe_ajustado: Decimal | None = None
    precio_sugerido: Decimal | None = None
    margen_porcentaje: Decimal | None = None
    semaforo: str | None = None


def redondear_entero(valor: Decimal) -> int:
    return int(valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def redondear_precio(valor: Decimal, multiplo: Decimal) -> Decimal:
    return (valor / multiplo).quantize(Decimal("1"), rounding=ROUND_CEILING) * multiplo


def _validar(entrada: EntradaCosteo) -> list[Bloqueo]:
    bloqueos: list[Bloqueo] = []
    pool = entrada.gastos_fijos + entrada.gastos_variables + entrada.depreciacion
    if pool <= CERO:
        bloqueos.append(
            Bloqueo(
                CodigoBloqueo.SIN_COSTOS_INDIRECTOS_REGISTRADOS,
                3,
                "Registra gastos de tu consultorio",
            )
        )
    if (
        entrada.dias_por_semana is None
        or entrada.horas_por_dia is None
        or entrada.porcentaje_ocupacion is None
    ):
        bloqueos.append(Bloqueo(CodigoBloqueo.SIN_PERFIL_CAPACIDAD, 4, "Indica cuándo atiendes"))
    if not 1 <= entrada.duracion_clinica <= 600:
        bloqueos.append(
            Bloqueo(
                CodigoBloqueo.DURACION_INVALIDA,
                5,
                "El tiempo en sillón debe estar entre 1 y 600 minutos",
                "duracion_clinica",
            )
        )
    if entrada.espaciado is None:
        bloqueos.append(
            Bloqueo(
                CodigoBloqueo.SIN_ESPACIADO_PREDETERMINADO,
                5,
                "Configura el tiempo predeterminado del consultorio o elige un espaciado para este tratamiento",
                "espaciado",
            )
        )
    elif not 0 <= entrada.espaciado <= 15:
        bloqueos.append(
            Bloqueo(
                CodigoBloqueo.ESPACIADO_FUERA_RANGO,
                5,
                "El tiempo entre pacientes debe estar entre 0 y 15 minutos",
                "espaciado",
            )
        )
    if entrada.metodo_materiales is None:
        bloqueos.append(
            Bloqueo(
                CodigoBloqueo.SIN_METODO_MATERIALES,
                6,
                "Elige cómo registrar los materiales",
                "metodo_materiales",
            )
        )
    elif entrada.metodo_materiales == "PROMEDIO_MENSUAL" and entrada.materiales_generales is None:
        bloqueos.append(
            Bloqueo(
                CodigoBloqueo.SIN_MESES_VALIDOS,
                6,
                "Registra un mes con consumo y tratamientos atendidos",
            )
        )
    elif entrada.metodo_materiales == "IMPORTE_RAPIDO" and (
        entrada.materiales_generales is None or entrada.materiales_generales <= CERO
    ):
        bloqueos.append(
            Bloqueo(
                CodigoBloqueo.IMPORTE_MATERIALES_FALTANTE,
                6,
                "Indica un aproximado de materiales mayor que $0",
                "importe_materiales",
            )
        )
    elif entrada.metodo_materiales == "RECETA_INSUMOS" and (
        entrada.materiales_generales is None or entrada.materiales_generales <= CERO
    ):
        bloqueos.append(Bloqueo(CodigoBloqueo.RECETA_INCOMPLETA, 6, "Completa la receta", "receta"))
    elif entrada.materiales_generales is not None and entrada.materiales_generales <= CERO:
        bloqueos.append(
            Bloqueo(CodigoBloqueo.MATERIALES_EN_CERO, 6, "Los materiales deben ser mayores que $0")
        )
    if not Decimal("1") <= entrada.ajuste_porcentaje <= Decimal("500"):
        bloqueos.append(
            Bloqueo(
                CodigoBloqueo.AJUSTE_FUERA_RANGO,
                7,
                "El ajuste debe estar entre 1% y 500%",
                "ajuste_porcentaje",
            )
        )
    return bloqueos


def calcular_costeo(entrada: EntradaCosteo) -> ResultadoCosteo:
    bloqueos = _validar(entrada)
    pool = entrada.gastos_fijos + entrada.gastos_variables + entrada.depreciacion
    disponibles: int | None = None
    efectivos: int | None = None
    if (
        entrada.dias_por_semana is not None
        and entrada.horas_por_dia is not None
        and entrada.porcentaje_ocupacion is not None
    ):
        disponibles = redondear_entero(
            Decimal(entrada.dias_por_semana)
            * Decimal(52)
            / Decimal(12)
            * entrada.horas_por_dia
            * Decimal(60)
        )
        efectivos = redondear_entero(Decimal(disponibles) * entrada.porcentaje_ocupacion / CIEN)
        if efectivos <= 0:
            bloqueos.append(
                Bloqueo(
                    CodigoBloqueo.SIN_TIEMPO_ATENCION,
                    4,
                    "Sin tiempo de atención para calcular — revisa la ocupación.",
                )
            )
    if bloqueos:
        return ResultadoCosteo(
            False,
            tuple(bloqueos),
            pool_mensual=pool,
            minutos_disponibles=disponibles,
            minutos_efectivos=efectivos,
        )
    assert efectivos is not None and efectivos > 0
    assert entrada.materiales_generales is not None
    costo_minuto = pool / Decimal(efectivos)
    assert entrada.espaciado is not None
    minutos_imputados = entrada.duracion_clinica + entrada.espaciado
    costo_tiempo = Decimal(minutos_imputados) * costo_minuto
    costo_total = costo_tiempo + entrada.materiales_generales + entrada.materiales_especiales
    importe_ajustado = costo_total * (Decimal("1") + entrada.ajuste_porcentaje / CIEN)
    precio_sugerido = redondear_precio(importe_ajustado, entrada.multiplo_redondeo)
    margen = ((precio_sugerido - costo_total) / precio_sugerido * CIEN) if precio_sugerido else CERO
    semaforo = (
        "BAJO" if margen < Decimal("30") else "INTERMEDIO" if margen < Decimal("50") else "ALTO"
    )
    return ResultadoCosteo(
        completo=True,
        pool_mensual=pool,
        minutos_disponibles=disponibles,
        minutos_efectivos=efectivos,
        costo_por_minuto=costo_minuto,
        minutos_imputados=minutos_imputados,
        costo_tiempo=costo_tiempo,
        materiales_generales=entrada.materiales_generales,
        materiales_especiales=entrada.materiales_especiales,
        costo_total=costo_total,
        importe_ajustado=importe_ajustado,
        precio_sugerido=precio_sugerido,
        margen_porcentaje=margen,
        semaforo=semaforo,
    )
