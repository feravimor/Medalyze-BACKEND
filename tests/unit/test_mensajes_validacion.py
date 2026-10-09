import pytest

from app.api.mensajes_validacion import mensaje_de_validacion


@pytest.mark.parametrize(
    ("error", "esperado"),
    [
        ({"type": "missing", "msg": "Field required"}, "Este campo es obligatorio."),
        ({"type": "string_too_short", "msg": "x", "ctx": {"min_length": 1}}, "No puede estar vacío."),
        ({"type": "string_too_short", "msg": "x", "ctx": {"min_length": 10}}, "Debe tener al menos 10 caracteres."),
        ({"type": "string_too_long", "msg": "x", "ctx": {"max_length": 160}}, "Debe tener como máximo 160 caracteres."),
        ({"type": "too_short", "msg": "x", "ctx": {"min_length": 1}}, "Debe incluir al menos 1 elementos."),
        ({"type": "greater_than", "msg": "x", "ctx": {"gt": 0}}, "Debe ser mayor que 0."),
        ({"type": "greater_than_equal", "msg": "x", "ctx": {"ge": 1}}, "Debe ser mayor o igual que 1."),
        ({"type": "less_than_equal", "msg": "x", "ctx": {"le": 100}}, "Debe ser menor o igual que 100."),
        ({"type": "decimal_max_places", "msg": "x", "ctx": {"decimal_places": 2}}, "No admite más de 2 decimales."),
        ({"type": "decimal_parsing", "msg": "x"}, "Debe ser un número válido."),
        ({"type": "int_parsing", "msg": "x"}, "Debe ser un número válido."),
        ({"type": "date_from_datetime_parsing", "msg": "x"}, "Debe ser una fecha válida (AAAA-MM-DD)."),
        ({"type": "uuid_parsing", "msg": "x"}, "Debe ser un identificador válido."),
        ({"type": "literal_error", "msg": "x"}, "El valor no es una de las opciones permitidas."),
        ({"type": "extra_forbidden", "msg": "x"}, "Este campo no se admite."),
        ({"type": "json_invalid", "msg": "x"}, "El cuerpo de la solicitud no es un JSON válido."),
        (
            {"type": "value_error", "msg": "value is not a valid email address: An email address must have an @-sign."},
            "Escribe un correo electrónico válido.",
        ),
        (
            {"type": "value_error", "msg": "Value error, El valor de rescate debe ser menor que el costo del equipo."},
            "El valor de rescate debe ser menor que el costo del equipo.",
        ),
    ],
)
def test_traduce_los_errores_comunes_de_pydantic(error: dict, esperado: str) -> None:
    assert mensaje_de_validacion(error) == esperado


def test_un_tipo_desconocido_conserva_el_mensaje_original() -> None:
    assert mensaje_de_validacion({"type": "algo_nuevo", "msg": "Mensaje original"}) == "Mensaje original"
