from fastapi import APIRouter, Response, status

from app.core.config import obtener_configuracion
from app.core.database import comprobar_disponibilidad

router = APIRouter(tags=["Salud"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"estado": "ok", "version": obtener_configuracion().app_version}


@router.get("/ready")
def ready(response: Response) -> dict[str, str]:
    disponible = comprobar_disponibilidad()
    if not disponible:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "estado": "ok" if disponible else "no_disponible",
        "version": obtener_configuracion().app_version,
    }
