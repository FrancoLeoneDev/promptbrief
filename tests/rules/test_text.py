from promptbrief.core.models import Severity
from promptbrief.core.rules.text import TEXT_RULES

from .conftest import fired


def text_findings(text: str, **kwargs) -> dict[str, Severity]:
    return fired(TEXT_RULES, text=text, **kwargs)


def test_missing_success_criteria_fires_when_absent():
    assert "missing_success_criteria" in text_findings("agregar una seccion de python")


def test_missing_success_criteria_silent_when_provided():
    assert "missing_success_criteria" not in text_findings(
        "agregar una seccion", success_criteria="se ve igual que game dev"
    )


def test_dangling_reference_fires_on_a_pronoun_with_no_antecedent():
    assert "dangling_reference" in text_findings("arreglalo por favor")
    assert "dangling_reference" in text_findings("hace que ande")


def test_dangling_reference_silent_when_the_same_text_names_something_concrete():
    # Dispara _DANGLING ("arreglalo") y aun así calla por la guarda de antecedente.
    # Si se borra la guarda, este test falla.
    assert "dangling_reference" not in text_findings(
        "arreglalo, me refiero al componente de filtros"
    )


def test_vague_quantifier_fires_without_a_metric():
    assert "vague_quantifier" in text_findings("hacer que cargue mas rapido")


def test_vague_quantifier_silent_when_the_same_text_carries_a_metric():
    assert "vague_quantifier" not in text_findings(
        "hacer que cargue mas rapido: de 800ms a 200ms"
    )


def test_negative_instruction_is_info_severity():
    result = text_findings("agregar la seccion, no uses tailwind")
    assert result["negative_instruction"] == Severity.INFO


def test_negative_instruction_silent_on_positive_phrasing():
    assert "negative_instruction" not in text_findings("agregar la seccion usando css modules")


def test_multiple_unrelated_tasks_fires_on_an_enumeration():
    assert "multiple_unrelated_tasks" in text_findings(
        "agregar la seccion de python, arreglar el favicon y ademas escribir el readme"
    )


def test_multiple_unrelated_tasks_silent_on_multiple_semicolons_in_a_code_snippet():
    # Un punto y coma no es un marcador de enumeración, ni siquiera repetido: un
    # snippet de código pegado en el pedido no puede disparar la regla. Guard real
    # contra el riesgo que el comentario de _TASK_SEPARATOR dice estar evitando
    # (que alguien agregue ";" a la lista de marcadores).
    assert "multiple_unrelated_tasks" not in text_findings(
        "agregar const x = 1; const y = 2; const z = 3 al helper de formato"
    )


def test_over_emphasis_fires_on_shouting():
    assert "over_emphasis" in text_findings("ES MUY IMPORTANTE que uses TypeScript SIEMPRE")


def test_over_emphasis_fires_on_shouted_word_count_alone():
    # Ningún token de este texto está en _EMPHASIS_WORD: el disparo pasa
    # exclusivamente por el conteo de _SHOUTED_WORD (MODAL, WIDGET) alcanzando
    # _MIN_SHOUTED_WORDS. Distingue este camino del de test_over_emphasis_fires_on_shouting,
    # que dispara por _EMPHASIS_WORD.
    assert "over_emphasis" in text_findings("revisar el MODAL y el WIDGET de configuracion")


def test_over_emphasis_silent_on_technical_acronyms():
    assert "over_emphasis" not in text_findings("actualizar README y CLAUDE.md con la convencion")
    assert "over_emphasis" not in text_findings("devolver JSON sobre HTTP usando REST")


def test_over_emphasis_silent_on_a_single_unknown_shouted_word():
    # Ejercita el umbral _MIN_SHOUTED_WORDS, no la lista de siglas.
    assert "over_emphasis" not in text_findings("revisar el TOOLTIP de la tabla")
