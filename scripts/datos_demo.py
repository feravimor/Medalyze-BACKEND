"""Carga un consultorio de demostración completo a través de la API.

Crea (o reutiliza) una cuenta, configura el consultorio y deja capturados gastos, equipos, insumos,
datos mensuales y siete tratamientos, seis de ellos ya calculados con los tres métodos de materiales.
Usa los mismos endpoints que la aplicación, así que los precios que se ven son los que calcula el motor.

Uso (con la API corriendo):
    python scripts/datos_demo.py
    python scripts/datos_demo.py --url http://127.0.0.1:8000/api/v1 --correo demo@medalyze.mx

Se puede ejecutar varias veces: lo que ya existe se reutiliza y no se duplica (también si una
ejecución anterior se interrumpió a la mitad: continúa donde se quedó). Solo usa la biblioteca
estándar. Es material de demostración: la contraseña por defecto no debe usarse en producción.
"""

from __future__ import annotations

import argparse
import json as jsonlib
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

CORREO = "demo@medalyze.mx"
CONTRASENA = "Demo-Medalyze-2026"
DOCTORA = "Dra. Ana Torres"
CONSULTORIO = "Clínica Dental Sonrisa"
ESPECIALIDADES = ("GENERAL", "ENDODONCIA", "ESTETICA")

# --- Capacidad de atención: 5 días a la semana, 8 horas al día, 70 % de ocupación.
CAPACIDAD: dict[str, Any] = {
    "dias_por_semana": 5,
    "horas_por_dia": "8",
    "porcentaje_ocupacion": "70",
}

# --- Gastos del consultorio: nombre, categoría, importe, periodicidad.
# Equivalen a $36,929.00 al mes (el sueldo quincenal vale el doble al mes; el seguro anual, 1/12).
GASTOS = [
    ("Renta del local", "FIJO", "18000", "MENSUAL"),
    ("Sueldo de asistente dental", "FIJO", "4750", "QUINCENAL"),
    ("Internet y telefonía", "FIJO", "899", "MENSUAL"),
    ("Software de gestión del consultorio", "FIJO", "1200", "MENSUAL"),
    ("Seguro de responsabilidad civil", "FIJO", "7800", "ANUAL"),
    ("Contador", "FIJO", "1500", "MENSUAL"),
    ("Mantenimiento de equipo", "FIJO", "6000", "SEMESTRAL"),
    ("Electricidad", "VARIABLE", "2400", "BIMESTRAL"),
    ("Agua", "VARIABLE", "380", "MENSUAL"),
    ("Limpieza y desechables", "VARIABLE", "1100", "MENSUAL"),
    ("Publicidad en redes sociales", "VARIABLE", "1500", "MENSUAL"),
]

# --- Equipos: nombre, precio, valor residual, vida útil en años, fecha de alta.
# Su depreciación mensual suma $3,068.75.
EQUIPOS = [
    ("Sillón dental", "180000", "20000", 10, "2024-03-01"),
    ("Compresor de aire", "28000", "3000", 8, "2024-03-01"),
    ("Autoclave", "36000", "4000", 8, "2024-05-15"),
    ("Lámpara de fotocurado", "6500", "500", 5, "2024-05-15"),
    ("Equipo de rayos X portátil", "95000", "10000", 10, "2025-01-10"),
    ("Computadora y software", "18000", "2000", 4, "2025-02-01"),
]

# --- Insumos: nombre, presentación, unidad, cantidad que contiene, precio de la presentación.
INSUMOS = [
    ("Guantes de nitrilo", "Caja", "PZA", "100", "180"),
    ("Cubrebocas", "Caja", "PZA", "50", "95"),
    ("Eyectores de saliva", "Bolsa", "PZA", "100", "75"),
    ("Gasas estériles", "Paquete", "PZA", "200", "160"),
    ("Pasta profiláctica", "Frasco", "G", "200", "210"),
    ("Anestésico lidocaína 2 %", "Caja", "PZA", "50", "650"),
    ("Agujas dentales cortas", "Caja", "PZA", "100", "320"),
    ("Resina compuesta", "Jeringa", "G", "4", "780"),
    ("Adhesivo dental", "Frasco", "ML", "5", "890"),
    ("Limas endodónticas", "Caja", "PZA", "6", "540"),
    ("Hipoclorito de sodio", "Botella", "ML", "1000", "65"),
    ("Gutapercha", "Caja", "PZA", "120", "380"),
    ("Sellador endodóntico", "Kit", "G", "10", "720"),
]

# --- Datos mensuales del mes actual y los dos anteriores: consumo de materiales y tratamientos atendidos.
PERIODOS = [
    ("2150", 47, "ESTE_MES"),
    ("1980", 44, "PERIODO_ANTERIOR"),
    ("2090", 46, "PERIODO_ANTERIOR"),
]

# --- Tratamientos. Cada receta: (insumo, cantidad, merma en %).
# Los porcentajes de ajuste buscan mostrar los tres colores del semáforo de margen.
TRATAMIENTOS: list[dict[str, Any]] = [
    {
        "nombre": "Limpieza dental (profilaxis)",
        "especialidad": "GENERAL",
        "duracion": 30,
        "ajuste": "100",
        "metodo": "RECETA_INSUMOS",
        "receta": [
            ("Guantes de nitrilo", "2", "0"),
            ("Cubrebocas", "1", "0"),
            ("Pasta profiláctica", "8", "10"),
            ("Eyectores de saliva", "1", "0"),
        ],
    },
    {
        "nombre": "Resina de una superficie",
        "especialidad": "GENERAL",
        "duracion": 45,
        "ajuste": "60",
        "metodo": "RECETA_INSUMOS",
        "receta": [
            ("Guantes de nitrilo", "2", "0"),
            ("Cubrebocas", "1", "0"),
            ("Anestésico lidocaína 2 %", "1", "0"),
            ("Agujas dentales cortas", "1", "0"),
            ("Resina compuesta", "0.6", "15"),
            ("Adhesivo dental", "0.15", "10"),
            ("Eyectores de saliva", "1", "0"),
            ("Gasas estériles", "2", "0"),
        ],
    },
    {
        "nombre": "Extracción simple",
        "especialidad": "GENERAL",
        "duracion": 40,
        "ajuste": "80",
        "metodo": "RECETA_INSUMOS",
        "receta": [
            ("Guantes de nitrilo", "2", "0"),
            ("Cubrebocas", "1", "0"),
            ("Anestésico lidocaína 2 %", "2", "0"),
            ("Agujas dentales cortas", "1", "0"),
            ("Gasas estériles", "4", "0"),
            ("Eyectores de saliva", "1", "0"),
        ],
    },
    {
        "nombre": "Endodoncia unirradicular",
        "especialidad": "ENDODONCIA",
        "duracion": 90,
        "ajuste": "30",
        "metodo": "RECETA_INSUMOS",
        "receta": [
            ("Guantes de nitrilo", "4", "0"),
            ("Cubrebocas", "2", "0"),
            ("Anestésico lidocaína 2 %", "2", "0"),
            ("Agujas dentales cortas", "1", "0"),
            ("Limas endodónticas", "3", "0"),
            ("Hipoclorito de sodio", "20", "0"),
            ("Gutapercha", "10", "0"),
            ("Sellador endodóntico", "0.5", "0"),
            ("Gasas estériles", "6", "0"),
            ("Eyectores de saliva", "2", "0"),
        ],
    },
    {
        "nombre": "Blanqueamiento en consultorio",
        "especialidad": "ESTETICA",
        "duracion": 60,
        "ajuste": "110",
        "metodo": "IMPORTE_RAPIDO",
        "importe": "350",
        "receta": [],
    },
    {
        "nombre": "Revisión y diagnóstico",
        "especialidad": "GENERAL",
        "duracion": 20,
        "ajuste": "80",
        "metodo": "PROMEDIO_MENSUAL",
        "receta": [],
    },
    # Se deja en borrador a propósito: muestra cómo se ve un tratamiento sin configurar.
    {
        "nombre": "Corona de zirconia",
        "especialidad": "PROSTODONCIA",
        "duracion": 90,
        "calcular": False,
    },
]

# Un adaptador de transporte recibe (método, ruta, json, rev, clave, token) y devuelve (estado, cuerpo).
Llamar = Callable[..., tuple[int, Any]]


class ErrorDemo(Exception):
    """Algo falló al cargar los datos; el mensaje explica qué llamada y por qué."""


class _Api:
    def __init__(self, llamar: Llamar) -> None:
        self._llamar = llamar
        self.token: str | None = None

    def __call__(
        self,
        metodo: str,
        ruta: str,
        *,
        json: Any = None,
        rev: int | None = None,
        clave: str | None = None,
        esperar: tuple[int, ...] = (200, 201, 204),
    ) -> Any:
        estado, cuerpo = self._llamar(
            metodo, ruta, json=json, rev=rev, clave=clave, token=self.token
        )
        if esperar and estado not in esperar:
            detalle = (cuerpo or {}).get("detalle", cuerpo) if isinstance(cuerpo, dict) else cuerpo
            raise ErrorDemo(f"{metodo} {ruta} respondió {estado}: {detalle}")
        return cuerpo


def _existentes(api: _Api, ruta: str, campo: str) -> dict[str, dict[str, Any]]:
    separador = "&" if "?" in ruta else "?"
    return {e[campo]: e for e in api("GET", f"{ruta}{separador}limite=100")["elementos"]}


def _meses() -> list[str]:
    actual = date.today().replace(day=1)
    anterior = (actual - timedelta(days=1)).replace(day=1)
    antes = (anterior - timedelta(days=1)).replace(day=1)
    return [str(actual), str(anterior), str(antes)]


def _cuenta(api: _Api, correo: str, contrasena: str) -> None:
    estado, cuerpo = api._llamar(
        "POST",
        "/autenticacion/registro",
        json={
            "nombre_completo": DOCTORA,
            "correo": correo,
            "contrasena": contrasena,
            "nombre_consultorio": CONSULTORIO,
        },
        rev=None,
        clave=None,
        token=None,
    )
    if estado == 409:  # la cuenta ya existe: se inicia sesión
        estado, cuerpo = api._llamar(
            "POST",
            "/autenticacion/inicio-sesion",
            json={"correo": correo, "contrasena": contrasena},
            rev=None,
            clave=None,
            token=None,
        )
    if estado not in (200, 201):
        raise ErrorDemo(f"No se pudo crear ni abrir la cuenta {correo} ({estado}): {cuerpo}")
    api.token = cuerpo["token_acceso"]


def _consultorio(api: _Api) -> None:
    claves = {e["clave"]: e["identificador"] for e in api("GET", "/especialidades")["elementos"]}
    ids = [claves[c] for c in ESPECIALIDADES if c in claves]
    perfil = api("GET", "/perfil")
    if perfil.get("nombre_para_mostrar") != DOCTORA or sorted(
        perfil.get("especialidades", [])
    ) != sorted(ids):
        api(
            "PATCH",
            "/perfil",
            json={"nombre_para_mostrar": DOCTORA, "especialidades": ids},
            rev=perfil["revision"],
        )
    organizacion = api("GET", "/organizacion")
    if (
        float(organizacion["multiplo_redondeo"]) != 50
        or organizacion["espaciado_por_defecto"] != 10
    ):
        api(
            "PATCH",
            "/organizacion",
            json={"multiplo_redondeo": "50", "espaciado_por_defecto": 10},
            rev=organizacion["revision"],
        )
    onboarding = api("GET", "/onboarding")
    if not onboarding.get("completado"):
        api(
            "PATCH",
            "/onboarding",
            json={
                "ruta": "ASISTENTE_GUIADO",
                "situacion": "YA_ATIENDE_EN_CONSULTA_PRIVADA",
                "ultimo_paso": "finalizado",
                "completado": True,
            },
            rev=onboarding["revision"],
        )


def _capacidad(api: _Api) -> None:
    estado, actual = api._llamar(
        "GET", "/perfil-capacidad", json=None, rev=None, clave=None, token=api.token
    )
    if estado == 200:
        igual = (
            actual["dias_por_semana"] == CAPACIDAD["dias_por_semana"]
            and float(actual["horas_por_dia"]) == float(CAPACIDAD["horas_por_dia"])
            and float(actual["porcentaje_ocupacion"]) == float(CAPACIDAD["porcentaje_ocupacion"])
        )
        if igual:
            return
        revision = actual["revision"]
    elif estado == 404:
        revision = 0
    else:
        raise ErrorDemo(f"GET /perfil-capacidad respondió {estado}: {actual}")
    api("PUT", "/perfil-capacidad", json={**CAPACIDAD, "ocupacion_confirmada": True}, rev=revision)


def _costos(api: _Api) -> None:
    inicio = _meses()[-1]
    existentes = _existentes(api, "/gastos", "nombre")
    for nombre, categoria, importe, periodicidad in GASTOS:
        if nombre not in existentes:
            api(
                "POST",
                "/gastos",
                json={
                    "nombre": nombre,
                    "categoria": categoria,
                    "importe_pagado_por_periodo": importe,
                    "codigo_periodicidad": periodicidad,
                    "fecha_inicio_vigencia": inicio,
                    "activo": True,
                },
            )
    existentes = _existentes(api, "/equipos", "nombre")
    for nombre, precio, residual, vida, alta in EQUIPOS:
        if nombre not in existentes:
            api(
                "POST",
                "/equipos",
                json={
                    "nombre": nombre,
                    "precio_adquisicion": precio,
                    "valor_residual": residual,
                    "vida_util_anios": vida,
                    "fecha_alta_en_servicio": alta,
                    "estado": "ACTIVO",
                },
            )


def _insumos(api: _Api) -> dict[str, str]:
    existentes = _existentes(api, "/insumos?archivados=true", "nombre")
    for nombre, presentacion, unidad, cantidad, precio in INSUMOS:
        if nombre not in existentes:
            api(
                "POST",
                "/insumos",
                json={
                    "nombre": nombre,
                    "presentacion": presentacion,
                    "codigo_unidad": unidad,
                    "cantidad_contenida": cantidad,
                    "precio_presentacion": precio,
                },
            )
    return {
        nombre: e["identificador"]
        for nombre, e in _existentes(api, "/insumos?archivados=true", "nombre").items()
    }


def _periodos(api: _Api) -> None:
    existentes = _existentes(api, "/periodos-mensuales", "mes")
    for mes, (consumo, atendidos, procedencia) in zip(_meses(), PERIODOS, strict=True):
        if mes not in existentes:
            api(
                "POST",
                "/periodos-mensuales",
                json={
                    "mes": mes,
                    "consumo_materiales": consumo,
                    "tratamientos_atendidos": atendidos,
                    "procedencia": procedencia,
                    "notas": None,
                },
            )


def _tratamientos(
    api: _Api, insumos: dict[str, str], avisar: Callable[[str], None]
) -> list[dict[str, Any]]:
    existentes = _existentes(api, "/tratamientos?archivados=true", "nombre")
    resumen: list[dict[str, Any]] = []
    for datos in TRATAMIENTOS:
        nombre = datos["nombre"]
        avisar(f"   · {nombre}")
        if nombre in existentes:
            identificador = existentes[nombre]["identificador"]
        else:
            creado = api(
                "POST",
                "/tratamientos",
                clave=f"demo-{uuid.uuid4().hex}",
                json={
                    "nombre": nombre,
                    "especialidad": datos["especialidad"],
                    "duracion_clinica": datos["duracion"],
                },
            )
            identificador = creado["identificador"]
        detalle = api("GET", f"/tratamientos/{identificador}")
        if datos.get("calcular", True) and detalle["estado"] != "CALCULADO":
            falta = [i for i, _, _ in datos["receta"] if i not in insumos]
            if falta:
                raise ErrorDemo(f"Faltan insumos para «{nombre}»: {', '.join(falta)}")
            configuracion = {
                "nombre": nombre,
                "especialidad": datos["especialidad"],
                "duracion_clinica": datos["duracion"],
                "espaciado": None,
                "metodo_materiales": datos["metodo"],
                "importe_materiales": datos.get("importe"),
                "receta": [
                    {"identificador_insumo": insumos[i], "cantidad": c, "merma_porcentaje": m}
                    for i, c, m in datos["receta"]
                ],
                "ajuste_porcentaje": datos["ajuste"],
            }
            detalle = api(
                "PUT",
                f"/tratamientos/{identificador}/configuracion",
                json=configuracion,
                rev=detalle["revision"],
            )
            api(
                "POST",
                f"/tratamientos/{identificador}/calculos",
                clave=f"demo-{uuid.uuid4().hex}",
                json={"revision_tratamiento": detalle["revision"]},
                rev=detalle["revision"],
            )
            detalle = api("GET", f"/tratamientos/{identificador}")
        resultado = detalle.get("ultimo_resultado") or {}
        resumen.append(
            {
                "nombre": nombre,
                "estado": detalle["estado"],
                "metodo": datos.get("metodo", "—"),
                "costo_total": resultado.get("costo_total"),
                "precio_sugerido": resultado.get("precio_sugerido"),
                "margen_porcentaje": resultado.get("margen_porcentaje"),
                "semaforo": resultado.get("semaforo"),
            }
        )
    return resumen


def cargar_datos_demo(
    llamar: Llamar,
    correo: str = CORREO,
    contrasena: str = CONTRASENA,
    avisar: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Carga el consultorio de demostración y devuelve un resumen de lo que quedó.

    ``avisar`` recibe un mensaje al empezar cada etapa (la línea de comandos lo imprime).
    """
    paso = avisar or (lambda _mensaje: None)
    api = _Api(llamar)
    paso("1/6 Cuenta de demostración…")
    _cuenta(api, correo, contrasena)
    paso("2/6 Consultorio y capacidad de atención…")
    _consultorio(api)
    _capacidad(api)
    paso("3/6 Gastos y equipos…")
    _costos(api)
    paso("4/6 Insumos…")
    insumos = _insumos(api)
    paso("5/6 Datos mensuales…")
    _periodos(api)
    paso("6/6 Tratamientos y cálculo de precios…")
    tratamientos = _tratamientos(api, insumos, paso)
    costos = api("GET", "/costos-indirectos/resumen")
    return {
        "correo": correo,
        "costos_indirectos": {
            campo: costos.get(campo)
            for campo in (
                "gastos_fijos",
                "gastos_variables",
                "depreciacion",
                "total_mensual",
                "costo_por_minuto",
            )
        },
        "conteos": {
            "gastos": len(GASTOS),
            "equipos": len(EQUIPOS),
            "insumos": len(INSUMOS),
            "periodos": len(PERIODOS),
            "tratamientos": len(TRATAMIENTOS),
        },
        "tratamientos": tratamientos,
    }


def _transporte_http(base: str) -> Llamar:
    def llamar(
        metodo: str,
        ruta: str,
        json: Any = None,
        rev: int | None = None,
        clave: str | None = None,
        token: str | None = None,
    ) -> tuple[int, Any]:
        cabeceras = {"Accept": "application/json"}
        datos = None
        if json is not None:
            datos = jsonlib.dumps(json).encode("utf-8")
            cabeceras["Content-Type"] = "application/json"
        if token:
            cabeceras["Authorization"] = f"Bearer {token}"
        if rev is not None:
            cabeceras["If-Match"] = str(rev)
        if clave:
            cabeceras["Idempotency-Key"] = clave
        solicitud = urllib.request.Request(
            base + ruta, data=datos, method=metodo, headers=cabeceras
        )
        try:
            with urllib.request.urlopen(solicitud, timeout=30) as respuesta:
                estado, crudo = respuesta.status, respuesta.read()
        except urllib.error.HTTPError as error:
            estado, crudo = error.code, error.read()
        except urllib.error.URLError as error:
            raise ErrorDemo(f"No se pudo conectar con la API en {base}: {error.reason}") from error
        return estado, (jsonlib.loads(crudo) if crudo else None)

    return llamar


def _imprimir(resumen: dict[str, Any]) -> None:
    costos = resumen["costos_indirectos"]
    dinero = lambda valor: f"${float(valor):,.2f}"  # noqa: E731
    print(f"\nConsultorio de demostración listo para {resumen['correo']}")
    print(
        f"Costos indirectos al mes: {dinero(costos['total_mensual'])} "
        f"(gastos fijos {dinero(costos['gastos_fijos'])} · variables {dinero(costos['gastos_variables'])} "
        f"· depreciación {dinero(costos['depreciacion'])})"
    )
    print(f"Costo por minuto de consulta: {dinero(costos['costo_por_minuto'])}\n")
    print(f"{'Tratamiento':<32}{'Estado':<22}{'Costo':>10}{'Precio':>10}{'Margen':>9}  Semáforo")
    for t in resumen["tratamientos"]:
        costo = f"${float(t['costo_total']):,.2f}" if t["costo_total"] else "—"
        precio = f"${float(t['precio_sugerido']):,.0f}" if t["precio_sugerido"] else "—"
        margen = f"{t['margen_porcentaje']:.1f} %" if t["margen_porcentaje"] is not None else "—"
        print(
            f"{t['nombre']:<32}{t['estado']:<22}{costo:>10}{precio:>10}{margen:>9}  {t['semaforo'] or '—'}"
        )


def main() -> int:
    analizador = argparse.ArgumentParser(
        description="Carga un consultorio de demostración a través de la API."
    )
    analizador.add_argument(
        "--url", default=os.getenv("MEDALYZE_API_URL", "http://127.0.0.1:8000/api/v1")
    )
    analizador.add_argument("--correo", default=CORREO)
    analizador.add_argument("--contrasena", default=CONTRASENA)
    argumentos = analizador.parse_args()
    inicio = time.monotonic()
    print(f"Cargando la demostración en {argumentos.url}…", flush=True)
    try:
        resumen = cargar_datos_demo(
            _transporte_http(argumentos.url.rstrip("/")),
            argumentos.correo,
            argumentos.contrasena,
            avisar=lambda mensaje: print(mensaje, flush=True),
        )
    except ErrorDemo as error:
        print(f"\nNo se pudo cargar la demostración: {error}", file=sys.stderr)
        return 1
    _imprimir(resumen)
    print(f"\nInicia sesión con: {argumentos.correo} / {argumentos.contrasena}")
    print(f"Listo en {time.monotonic() - inicio:.0f} s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
