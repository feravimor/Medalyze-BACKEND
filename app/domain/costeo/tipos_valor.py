from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Dinero:
    valor: Decimal

    def __post_init__(self) -> None:
        if not self.valor.is_finite():
            raise ValueError("El importe debe ser finito.")


@dataclass(frozen=True, slots=True)
class Minutos:
    valor: int

    def __post_init__(self) -> None:
        if self.valor < 0:
            raise ValueError("Los minutos no pueden ser negativos.")


@dataclass(frozen=True, slots=True)
class Porcentaje:
    valor: Decimal

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.valor <= Decimal("500"):
            raise ValueError("El porcentaje debe estar entre 0 y 500.")
