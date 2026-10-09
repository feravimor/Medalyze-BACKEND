"""Mensajes de validación en español para los errores por campo.

Pydantic describe los errores en inglés («String should have at least 10 characters»). La API los
devuelve en ``detalle.campos[].mensaje`` y el frontend puede mostrarlos tal cual, así que aquí se
traducen los tipos de error más comunes. Un tipo que no se conoce conserva el mensaje original.
"""

from typing import Any

_FECHA = "Debe ser una fecha válida (AAAA-MM-DD)."
_NUMERO = "Debe ser un número válido."


def mensaje_de_validacion(error: dict[str, Any]) -> str:
    tipo = str(error.get("type", ""))
    contexto: dict[str, Any] = error.get("ctx") or {}
    original = str(error.get("msg", ""))

    if tipo == "missing":
        return "Este campo es obligatorio."
    if tipo == "string_too_short":
        minimo = contexto.get("min_length")
        return "No puede estar vacío." if minimo == 1 else f"Debe tener al menos {minimo} caracteres."
    if tipo == "string_too_long":
        return f"Debe tener como máximo {contexto.get('max_length')} caracteres."
    if tipo == "too_short":
        return f"Debe incluir al menos {contexto.get('min_length')} elementos."
    if tipo == "too_long":
        return f"Debe incluir como máximo {contexto.get('max_length')} elementos."
    if tipo == "greater_than":
        return f"Debe ser mayor que {contexto.get('gt')}."
    if tipo == "greater_than_equal":
        return f"Debe ser mayor o igual que {contexto.get('ge')}."
    if tipo == "less_than":
        return f"Debe ser menor que {contexto.get('lt')}."
    if tipo == "less_than_equal":
        return f"Debe ser menor o igual que {contexto.get('le')}."
    if tipo == "decimal_max_places":
        return f"No admite más de {contexto.get('decimal_places')} decimales."
    if tipo in ("decimal_parsing", "decimal_type", "int_parsing", "int_type", "int_from_float", "float_parsing", "float_type"):
        return _NUMERO
    if tipo in ("date_parsing", "date_from_datetime_parsing", "date_type"):
        return _FECHA
    if tipo in ("uuid_parsing", "uuid_type"):
        return "Debe ser un identificador válido."
    if tipo in ("bool_parsing", "bool_type"):
        return "Debe ser verdadero o falso."
    if tipo == "string_type":
        return "Debe ser texto."
    if tipo == "literal_error":
        return "El valor no es una de las opciones permitidas."
    if tipo == "extra_forbidden":
        return "Este campo no se admite."
    if tipo == "json_invalid":
        return "El cuerpo de la solicitud no es un JSON válido."
    if tipo == "value_error":
        if "email address" in original:
            return "Escribe un correo electrónico válido."
        # Nuestras propias reglas ya vienen en español; solo se quita el prefijo de Pydantic.
        return original.removeprefix("Value error, ")
    return original
