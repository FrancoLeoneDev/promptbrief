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
        "subir el limite a 1500 tokens",       # "500" dentro de "1500"
    ],
)
def test_signals_do_not_match_inside_longer_words(text):
    assert classify(text) == TaskType.CODE_CHANGE


def test_unrecognized_text_falls_back_to_code_change():
    assert classify("mmm no se") == TaskType.CODE_CHANGE
