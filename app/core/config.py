import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

SECRETO_DE_DESARROLLO = "solo-desarrollo-cambiar-este-secreto-32"


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_version: str = "dev"
    database_url: str = "postgresql+psycopg://medalyze:medalyze@localhost:5432/medalyze"
    jwt_secret: str = Field(default=SECRETO_DE_DESARROLLO, min_length=32)
    jwt_access_ttl_min: int = Field(default=15, ge=1, le=60)
    refresh_ttl_days: int = Field(default=7, ge=1, le=30)
    # NoDecode: pydantic-settings NO intenta leer el valor como JSON antes del validador.
    # Sin esto, CORS_ORIGINS=http://localhost:5173 falla al arrancar (SettingsError).
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def separar_origenes(cls, value: object) -> object:
        """Acepta una lista JSON ('["http://a","http://b"]') o texto separado por comas."""
        if isinstance(value, str):
            texto = value.strip()
            if texto.startswith("["):
                return json.loads(texto)
            return [origen.strip() for origen in texto.split(",") if origen.strip()]
        return value

    @model_validator(mode="after")
    def exigir_secreto_real_fuera_de_local(self) -> "Configuracion":
        """Evita arrancar en un ambiente real con un secreto JWT público (cualquiera forjaría tokens)."""
        if self.app_env not in {"local", "test"} and self.jwt_secret == SECRETO_DE_DESARROLLO:
            raise ValueError("JWT_SECRET debe definirse explícitamente fuera de APP_ENV=local.")
        return self


@lru_cache
def obtener_configuracion() -> Configuracion:
    return Configuracion()
