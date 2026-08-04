from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from promptbrief.core.models import Profile, Slot


@dataclass(frozen=True)
class ProfileDiff:
    """Qué cambió entre dos destilaciones del mismo proyecto.

    `modified` lleva pares (antes, después) para que la UI muestre los dos lados.
    """

    added: tuple[Slot, ...] = ()
    removed: tuple[Slot, ...] = ()
    modified: tuple[tuple[Slot, Slot], ...] = ()
    unchanged: tuple[Slot, ...] = ()

    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.modified)


def _pair_key(slot: Slot) -> tuple[str, str]:
    """Identidad aproximada de un slot, independiente de su contenido."""
    return (slot.source.file if slot.source else "", slot.kind.value)


def _line(slot: Slot) -> int:
    return slot.source.line if slot.source else 0


def _same(before: Slot, after: Slot) -> bool:
    """Igualdad observable de dos slots emparejados.

    El id no incluye `needs_review` ni la línea, así que dos slots pueden compartirlo
    y aun así comportarse distinto: uno que pasa a `needs_review` deja de inyectarse.

    El contenido entra en la comparación aunque para dos ids iguales sea redundante
    —el id sale de un hash del contenido—, porque el emparejamiento por cercanía junta
    slots de ids distintos y ahí sí puede caer un par idéntico: el bullet que no se
    tocó al lado del que sí. Reportarlo como editado sería inventar un cambio.
    """
    return (
        before.content == after.content
        and before.needs_review == after.needs_review
        and before.redacted == after.redacted
        and before.applies_to == after.applies_to
        and _line(before) == _line(after)
    )


def _pair_by_proximity(
    before: list[Slot], after: list[Slot]
) -> tuple[list[tuple[Slot, Slot]], list[Slot], list[Slot]]:
    """Empareja greedy por cercanía de línea. Lo que sobra queda sin par.

    Emparejar solo cuando hay uno de cada lado dejaba sin resolver el caso más común
    —editar un bullet y agregar otro bajo el mismo heading— y lo reportaba como churn.
    """
    pending_after = sorted(after, key=_line)
    pairs: list[tuple[Slot, Slot]] = []
    unpaired_before: list[Slot] = []

    for old_slot in sorted(before, key=_line):
        if not pending_after:
            unpaired_before.append(old_slot)
            continue
        closest = min(pending_after, key=lambda new: abs(_line(new) - _line(old_slot)))
        pending_after.remove(closest)
        pairs.append((old_slot, closest))

    return pairs, unpaired_before, pending_after


def diff_profiles(old: Profile, new: Profile) -> ProfileDiff:
    """Reconcilia dos destilaciones del mismo proyecto.

    Los ids derivan del contenido, así que un bullet editado aparece como un id nuevo
    que reemplaza a uno viejo. Sin reconciliación, toda edición se vería como un
    agregado más un borrado.

    El emparejamiento por cercanía de línea es una heurística y puede errar cuando se
    reordenan varios bullets a la vez; el costo de errar es mostrar un par raro, no
    perder información: los dos lados están en el resultado igual.
    """
    old_by_id = {slot.id: slot for slot in old.slots}
    new_by_id = {slot.id: slot for slot in new.slots}
    shared = old_by_id.keys() & new_by_id.keys()

    unchanged: list[Slot] = []
    modified: list[tuple[Slot, Slot]] = []
    for slot_id, slot in new_by_id.items():
        if slot_id not in shared:
            continue
        if _same(old_by_id[slot_id], slot):
            unchanged.append(slot)
        else:
            modified.append((old_by_id[slot_id], slot))

    pending_old: dict[tuple[str, str], list[Slot]] = defaultdict(list)
    pending_new: dict[tuple[str, str], list[Slot]] = defaultdict(list)
    for slot in old.slots:
        if slot.id not in shared:
            pending_old[_pair_key(slot)].append(slot)
    for slot in new.slots:
        if slot.id not in shared:
            pending_new[_pair_key(slot)].append(slot)

    added: list[Slot] = []
    removed: list[Slot] = []
    # sorted() y no la unión de sets: el orden de un set de tuplas depende de
    # PYTHONHASHSEED y cambiaría entre requests.
    for key in sorted(pending_old.keys() | pending_new.keys()):
        pairs, unpaired_old, unpaired_new = _pair_by_proximity(
            pending_old.get(key, []), pending_new.get(key, [])
        )
        for before, after in pairs:
            if _same(before, after):
                unchanged.append(after)
            else:
                modified.append((before, after))
        removed.extend(unpaired_old)
        added.extend(unpaired_new)

    return ProfileDiff(
        added=tuple(added),
        removed=tuple(removed),
        modified=tuple(modified),
        unchanged=tuple(unchanged),
    )
