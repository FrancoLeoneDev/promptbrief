import pytest

from promptbrief.core.models import TaskType
from promptbrief.core.tasks import REQUIRED_SLOTS, tasks_requiring


def test_every_task_type_declares_its_required_slots():
    assert set(REQUIRED_SLOTS) == set(TaskType)


def test_success_criteria_is_required_everywhere():
    for required in REQUIRED_SLOTS.values():
        assert "success_criteria" in required


def test_debug_requires_repro_and_expected_vs_actual():
    assert {"repro_steps", "expected_vs_actual"} <= REQUIRED_SLOTS[TaskType.DEBUG]


def test_writing_requires_examples_and_does_not_require_file_scope():
    assert "examples" in REQUIRED_SLOTS[TaskType.WRITING]
    assert "file_scope" not in REQUIRED_SLOTS[TaskType.WRITING]


def test_tasks_requiring_inverts_the_mapping():
    assert set(tasks_requiring("file_scope")) == {TaskType.CODE_CHANGE, TaskType.DEBUG}
    assert tasks_requiring("examples") == (TaskType.WRITING,)
    assert tasks_requiring("nonexistent") == ()


def test_required_slots_cannot_be_mutated():
    with pytest.raises(TypeError):
        REQUIRED_SLOTS[TaskType.CODE_CHANGE] = frozenset()
