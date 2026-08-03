import pytest

from promptbrief.core.classify import classify
from promptbrief.core.models import TaskType


@pytest.mark.parametrize(
    "text,expected",
    [
        ("quiero agregar una seccion nueva al portfolio", TaskType.CODE_CHANGE),
        ("add a dark mode toggle to the navbar", TaskType.CODE_CHANGE),
        ("el carrito tira error 500 cuando agrego un producto", TaskType.DEBUG),
        ("this test is failing and I don't know why", TaskType.DEBUG),
        ("escribir un post de linkedin sobre el sistema de inventario", TaskType.WRITING),
        ("draft the README for this repo", TaskType.WRITING),
        # Mixto: arreglar algo que se rompe al agregar es debug, no feature.
        ("arreglar el error que aparece al agregar un producto", TaskType.DEBUG),
    ],
)
def test_classify_detects_the_task_type(text, expected):
    assert classify(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "agregar un indice en postgres",       # "post" dentro de "postgres"
        "ajustar el padding del address bar",  # "add" dentro de "padding"/"address"
        # "bug" dentro de "debug": sin "\b" antes, "bug" matchearía y clasificaría
        # DEBUG. Ninguna señal dispara, así que cae al fallback de CODE_CHANGE.
        "activar el modo debug del compilador",
    ],
)
def test_signals_do_not_match_inside_longer_words(text):
    assert classify(text) == TaskType.CODE_CHANGE


def test_unrecognized_text_falls_back_to_code_change():
    assert classify("mmm no se") == TaskType.CODE_CHANGE


@pytest.mark.parametrize(
    "text",
    [
        # "error"/"bug" como sustantivo compuesto de vocabulario técnico normal:
        # no son un reporte de falla, así que no deben disparar DEBUG.
        "refactorizar el error handler",
        "revisar el error boundary del componente",
        "el sistema muestra un error message al usuario",
    ],
)
def test_error_as_a_compound_noun_does_not_trigger_debug(text):
    assert classify(text) == TaskType.CODE_CHANGE


def test_bug_glued_to_a_hyphen_does_not_trigger_debug():
    # El guion es un carácter no-palabra: "\b" solo no alcanza para evitar que "bug"
    # matchee dentro de "bug-free" (significa justo lo contrario de un reporte de
    # falla). Ninguna otra señal aparece en el texto, así que cae al fallback.
    assert classify("bug-free release notes") == TaskType.CODE_CHANGE


def test_post_glued_to_a_hyphen_does_not_trigger_writing():
    # Mismo mecanismo que con "bug-free": "post" no debe matchear dentro de
    # "post-mortem". Acá sí hay otra señal en el texto ("crear"), así que el
    # resultado es CODE_CHANGE por esa señal, no por fallback.
    assert classify("crear un post-mortem") == TaskType.CODE_CHANGE


def test_migrate_is_a_code_change_signal():
    assert classify("migrate the database") == TaskType.CODE_CHANGE
