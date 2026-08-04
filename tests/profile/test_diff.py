from promptbrief.core.models import Profile, Provenance, Slot, SlotKind
from promptbrief.core.profile.diff import diff_profiles


def slot(id_, content, *, file="CLAUDE.md", line=1, kind=SlotKind.CONVENTION,
         needs_review=False):
    return Slot(
        id=id_, kind=kind, content=content, applies_to=(),
        source=Provenance(file=file, line=line), needs_review=needs_review,
    )


def profile(*slots):
    return Profile(name="demo", root="/tmp", slots=slots, sources=())


def test_identical_profiles_have_no_changes():
    result = diff_profiles(profile(slot("a", "uno")), profile(slot("a", "uno")))
    assert result.is_empty()
    assert [s.id for s in result.unchanged] == ["a"]


def test_two_empty_profiles_do_not_break():
    assert diff_profiles(profile(), profile()).is_empty()


def test_a_new_slot_is_added_and_a_deleted_one_is_removed():
    result = diff_profiles(
        profile(slot("a", "uno", line=1)),
        profile(slot("a", "uno", line=1), slot("b", "dos", line=2, kind=SlotKind.CONSTRAINT)),
    )
    assert [s.id for s in result.added] == ["b"]
    assert result.removed == ()


def test_an_edited_slot_is_modified_not_add_plus_remove():
    old = profile(slot("aaaa", "usar pnpm", line=4))
    new = profile(slot("bbbb", "usar pnpm, nunca npm", line=4))
    result = diff_profiles(old, new)

    assert result.added == () and result.removed == ()
    before, after = result.modified[0]
    assert (before.content, after.content) == ("usar pnpm", "usar pnpm, nunca npm")


def test_editing_one_bullet_while_adding_another_still_pairs_the_edit():
    # El caso más común al tocar un CLAUDE.md, y el que la v1 no resolvía.
    old = profile(slot("a1", "usar pnpm", line=4), slot("a2", "usar vitest", line=5))
    new = profile(
        slot("b1", "usar pnpm", line=4),
        slot("b2", "usar vitest, no jest", line=5),
        slot("b3", "usar biome", line=6),
    )
    result = diff_profiles(old, new)

    assert [s.id for s in result.added] == ["b3"]
    assert result.removed == ()
    assert len(result.modified) == 1
    assert result.modified[0][1].content == "usar vitest, no jest"


def test_pairing_prefers_the_closest_line():
    old = profile(slot("a1", "primero", line=2), slot("a2", "segundo", line=20))
    new = profile(slot("b1", "PRIMERO", line=3), slot("b2", "SEGUNDO", line=21))
    result = diff_profiles(old, new)

    pairs = {before.content: after.content for before, after in result.modified}
    assert pairs == {"primero": "PRIMERO", "segundo": "SEGUNDO"}


def test_edits_in_different_files_or_kinds_do_not_get_paired():
    assert diff_profiles(
        profile(slot("a", "uno", file="CLAUDE.md")),
        profile(slot("b", "dos", file="README.md")),
    ).modified == ()
    assert diff_profiles(
        profile(slot("a", "uno", kind=SlotKind.CONVENTION)),
        profile(slot("b", "dos", kind=SlotKind.CONSTRAINT)),
    ).modified == ()


def test_a_change_that_keeps_the_id_is_still_reported():
    # Un fence sin cerrar pone needs_review=True en todos los slots sin tocar el
    # contenido, así que el id no cambia y el slot deja de inyectarse. Decir
    # "no cambió nada" sería mentir.
    old = profile(slot("a", "usar pnpm", needs_review=False))
    new = profile(slot("a", "usar pnpm", needs_review=True))
    result = diff_profiles(old, new)

    assert not result.is_empty()
    assert len(result.modified) == 1
    assert result.modified[0][1].needs_review is True
    assert result.unchanged == ()


def test_a_moved_line_is_reported_too():
    old = profile(slot("a", "usar pnpm", line=4))
    new = profile(slot("a", "usar pnpm", line=9))
    result = diff_profiles(old, new)
    assert len(result.modified) == 1
    assert result.unchanged == ()


def test_the_output_order_is_deterministic():
    # Iterar sobre la unión de dos sets depende de PYTHONHASHSEED. Para una pantalla
    # de sync eso es una lista que se reordena sola en cada request.
    old = profile()
    new = profile(*(slot(f"n{i}", f"c{i}", file=f"F{i}.md") for i in range(6)))
    orders = {tuple(s.id for s in diff_profiles(old, new).added) for _ in range(5)}
    assert len(orders) == 1
    assert orders.pop() == ("n0", "n1", "n2", "n3", "n4", "n5")
