from fastapi import APIRouter

from app.api.rutas import (
    autenticacion,
    costeo,
    cuenta,
    inicio,
    insumos,
    mensuales,
    operacion,
    salud,
    tratamientos,
)

router = APIRouter()
router.include_router(salud.router)
router.include_router(autenticacion.router, prefix="/autenticacion", tags=["Autenticación"])
router.include_router(cuenta.router, tags=["Cuenta y onboarding"])
router.include_router(operacion.router, tags=["Tiempo y costos"])
router.include_router(insumos.router, tags=["Insumos"])
router.include_router(mensuales.router, tags=["Datos mensuales"])
router.include_router(tratamientos.router, tags=["Tratamientos"])
router.include_router(costeo.router, tags=["Costeo e historial"])
router.include_router(inicio.router, tags=["Inicio"])
