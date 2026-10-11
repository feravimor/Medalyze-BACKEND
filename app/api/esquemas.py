from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class Esquema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class RegistroEntrada(Esquema):
    nombre_completo: str = Field(min_length=1, max_length=160)
    correo: EmailStr
    contrasena: str = Field(min_length=10, max_length=128)
    nombre_consultorio: str | None = Field(default=None, max_length=160)


class InicioSesionEntrada(Esquema):
    correo: EmailStr
    contrasena: str


class RenovacionEntrada(Esquema):
    token_actualizacion: str | None = None


class PerfilActualizar(Esquema):
    nombre_para_mostrar: str | None = Field(default=None, max_length=160)
    especialidades: list[UUID] | None = None


class OrganizacionActualizar(Esquema):
    nombre_comercial: str | None = Field(default=None, max_length=160)
    codigo_moneda: Literal["MXN"] | None = None
    multiplo_redondeo: Decimal | None = Field(default=None, gt=0)
    espaciado_por_defecto: int | None = Field(default=None, ge=0, le=15)


class OnboardingActualizar(Esquema):
    ruta: Literal["ASISTENTE_GUIADO", "CAPTURA_DIRECTA_DATOS"] | None = None
    situacion: Literal["YA_ATIENDE_EN_CONSULTA_PRIVADA", "ESTA_POR_INICIAR"] | None = None
    ultimo_paso: str | None = None
    seleccion_parcial: dict[str, Any] | None = None
    completado: bool | None = None


class PerfilCapacidadEntrada(Esquema):
    dias_por_semana: int = Field(ge=1, le=7)
    horas_por_dia: Decimal = Field(ge=Decimal("0.01"), le=24, decimal_places=2)
    porcentaje_ocupacion: Decimal = Field(ge=0, le=100, decimal_places=2)
    ocupacion_confirmada: bool = False


class GastoEntrada(Esquema):
    nombre: str = Field(min_length=1, max_length=160)
    categoria: Literal["FIJO", "VARIABLE"]
    importe_pagado_por_periodo: Decimal = Field(ge=0)
    codigo_periodicidad: Literal[
        "SEMANAL", "QUINCENAL", "MENSUAL", "BIMESTRAL", "TRIMESTRAL", "SEMESTRAL", "ANUAL"
    ] = "MENSUAL"
    fecha_inicio_vigencia: date
    activo: bool = True


class EquipoEntrada(Esquema):
    nombre: str = Field(min_length=1, max_length=160)
    precio_adquisicion: Decimal = Field(gt=0)
    valor_residual: Decimal = Field(ge=0)
    vida_util_anios: int = Field(gt=0)
    fecha_alta_en_servicio: date | None = None
    estado: Literal["ACTIVO", "ARCHIVADO", "BAJA"] = "ACTIVO"

    @model_validator(mode="after")
    def validar_residual_menor_al_precio(self) -> "EquipoEntrada":
        # Antes era un método aparte que lanzaba ValueError (HTTP 500); ahora responde 422.
        if self.valor_residual >= self.precio_adquisicion:
            raise ValueError("El valor de rescate debe ser menor que el costo del equipo.")
        return self


class InsumoEntrada(Esquema):
    nombre: str = Field(min_length=1, max_length=160)
    presentacion: str | None = Field(default=None, max_length=60)
    codigo_unidad: str
    cantidad_contenida: Decimal = Field(gt=0)
    precio_presentacion: Decimal = Field(ge=0)


class PeriodoMensualEntrada(Esquema):
    mes: date
    consumo_materiales: Decimal = Field(ge=0)
    tratamientos_atendidos: int = Field(ge=0)
    procedencia: Literal["ESTE_MES", "PERIODO_ANTERIOR"]
    notas: str | None = None

    @field_validator("mes")
    @classmethod
    def primer_dia(cls, valor: date) -> date:
        if valor.day != 1:
            raise ValueError("El mes debe representarse con su primer día.")
        return valor


class CorreccionPeriodoEntrada(Esquema):
    consumo_materiales: Decimal = Field(ge=0)
    tratamientos_atendidos: int = Field(ge=0)
    procedencia: Literal["ESTE_MES", "PERIODO_ANTERIOR"]
    notas: str | None = None


class TratamientoEntrada(Esquema):
    nombre: str = Field(min_length=1, max_length=160)
    especialidad: str
    duracion_clinica: int = Field(ge=1, le=600)


class LineaRecetaEntrada(Esquema):
    identificador_insumo: UUID
    cantidad: Decimal = Field(gt=0)
    merma_porcentaje: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class ConfiguracionTratamientoEntrada(Esquema):
    nombre: str = Field(min_length=1, max_length=160)
    especialidad: str
    duracion_clinica: int = Field(ge=1, le=600)
    espaciado: int | None = Field(default=None, ge=0, le=15)
    metodo_materiales: Literal["PROMEDIO_MENSUAL", "IMPORTE_RAPIDO", "RECETA_INSUMOS"] | None = None
    importe_materiales: Decimal | None = Field(default=None, ge=0)
    receta: list[LineaRecetaEntrada] = Field(default_factory=list)
    ajuste_porcentaje: Decimal = Field(default=Decimal("1"), ge=1, le=500)


class VistaPreviaEntrada(Esquema):
    configuracion: ConfiguracionTratamientoEntrada | None = None


class CalculoEntrada(Esquema):
    revision_tratamiento: int = Field(ge=0)


class ImportarPlantillasEntrada(Esquema):
    claves: list[str] = Field(min_length=1)
    version_catalogo: Literal["2026-09-16.1"]


class CantidadTratamiento(Esquema):
    identificador_tratamiento: UUID
    cantidad: Decimal | None = Field(default=None, gt=0)


class VincularMaterialEntrada(Esquema):
    nombre_generico: str
    identificador_insumo: UUID
    cantidades: list[CantidadTratamiento]


class RespuestaPaginada(Esquema):
    elementos: list[dict[str, Any]]
    siguiente_cursor: str | None = None


def serializar_fila(fila: Any) -> dict[str, Any]:
    data = dict(fila._mapping if hasattr(fila, "_mapping") else fila)
    for clave, valor in list(data.items()):
        if isinstance(valor, (Decimal, UUID)):
            data[clave] = str(valor)
        elif isinstance(valor, (date, datetime)):
            data[clave] = valor.isoformat()
    return data
