from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_version: str = "dev"
    database_url: str = "postgresql+psycopg://medalyze:medalyze@localhost:5432/medalyze"
    jwt_secret: str = Field(default="solo-desarrollo-cambiar-este-secreto-32", min_length=32)
    jwt_access_ttl_min: int = Field(default=15, ge=1, le=60)
    refresh_ttl_days: int = Field(default=7, ge=1, le=30)
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def separar_origenes(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def obtener_configuracion() -> Configuracion:
    return Configuracion()
