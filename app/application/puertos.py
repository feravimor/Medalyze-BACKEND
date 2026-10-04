from decimal import Decimal
from typing import Protocol
from uuid import UUID


class RepositorioGastos(Protocol):
    def totales_mensuales(self, organizacion: UUID) -> tuple[Decimal, Decimal]: ...


class RepositorioEquipos(Protocol):
    def depreciacion_mensual(self, organizacion: UUID) -> Decimal: ...


class RepositorioConfiguracion(Protocol):
    def capacidad_vigente(self, organizacion: UUID) -> dict | None: ...

    def organizacion(self, identificador: UUID) -> dict: ...


class RepositorioTratamientos(Protocol):
    def obtener_con_configuracion(
        self, organizacion: UUID, tratamiento: UUID
    ) -> tuple[dict, dict] | None: ...


class RepositorioHojasCostos(Protocol):
    def detalle(self, organizacion: UUID, hoja: UUID) -> dict | None: ...


class RepositorioInsumos(Protocol):
    def precio_unitario_vigente(self, organizacion: UUID, insumo: UUID) -> Decimal | None: ...


class RepositorioPeriodosMensuales(Protocol):
    def periodos_elegibles(self, organizacion: UUID, limite: int = 3) -> list[dict]: ...


__all__ = [
    "RepositorioConfiguracion",
    "RepositorioEquipos",
    "RepositorioGastos",
    "RepositorioHojasCostos",
    "RepositorioInsumos",
    "RepositorioPeriodosMensuales",
    "RepositorioTratamientos",
]
