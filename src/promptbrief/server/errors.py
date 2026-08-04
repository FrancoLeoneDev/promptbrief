from __future__ import annotations

from fastapi import HTTPException

from promptbrief.core.errors import (
    ProfileAlreadyExists,
    ProfileNotFound,
    PromptBriefError,
    StoredProfileCorrupt,
)

# Solo lo que se aparta del genérico. El resto de la jerarquía es "el pedido está mal",
# que es exactamente un 400.
_STATUS_BY_TYPE: dict[type[PromptBriefError], int] = {
    ProfileNotFound: 404,
    ProfileAlreadyExists: 409,
    PromptBriefError: 400,
}

# Hereda de PromptBriefError, pero no es culpa del cliente: el YAML deformado está en
# el disco del servidor y reenviar otra cosa no lo arregla. Tiene que llegar como 500,
# así que el mapeo lo rechaza en vez de disfrazarlo de 4xx.
_NEVER_CLIENT_FAULT: tuple[type[PromptBriefError], ...] = (StoredProfileCorrupt,)


def to_http_exception(error: PromptBriefError) -> HTTPException:
    """Traduce un error de input a su 4xx. Levanta TypeError con cualquier otra cosa.

    El recorrido es sobre el MRO y no sobre `type(error)` exacto: una subclase futura
    de `ProfileNotFound` tiene que seguir siendo un 404 y no caer al genérico 400 por
    el solo hecho de no estar en la tabla.

    Rechazar en vez de devolver un 500 es deliberado: que un llamador pueda pedir el
    status de un `RuntimeError` y recibir algo plausible invita a envolver bugs
    internos en respuestas 4xx, que es justo lo que esconde los bugs.
    """
    if not isinstance(error, PromptBriefError) or isinstance(error, _NEVER_CLIENT_FAULT):
        raise TypeError(
            f"{type(error).__name__} no es culpa del pedido: tiene que caer a 500, "
            "no traducirse a un 4xx."
        )

    for ancestor in type(error).__mro__:
        status = _STATUS_BY_TYPE.get(ancestor)
        if status is not None:
            return HTTPException(status_code=status, detail=str(error))

    raise TypeError(f"{type(error).__name__} no tiene un status asignado.")
