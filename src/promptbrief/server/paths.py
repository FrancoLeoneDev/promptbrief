from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fastapi import HTTPException


def _looks_remote(raw: str) -> bool:
    """True si la *forma* del string apunta a otra máquina o a un device namespace.

    Cubre `\\\\host\\share` (UNC), `//host/share`, `\\\\?\\...` y `\\\\.\\...`: todos
    empiezan con dos separadores. Se mira el string y no un `Path` ya resuelto a
    propósito — ver `checked_root`.
    """
    return raw.replace("\\", "/").startswith("//")


def checked_root(raw: str, allowed: Sequence[Path]) -> Path:
    """La raíz de proyecto que pide el cliente, o un 403.

    Vive en su propio módulo y no pegada a un endpoint porque son cuatro las rutas que
    la necesitan, y una guarda que hay que acordarse de llamar es una guarda que en
    algún endpoint falta.

    El chequeo de forma va **antes** de `resolve()` y no después: resolver una UNC
    dispara la resolución DNS del host y un intento de conexión SMB en el acto, o sea
    que para cuando se compara contra la allowlist el daño ya está hecho — en Windows,
    una fuga del hash NTLM de la máquina hacia un host que eligió el atacante.

    No exige que la ruta exista: eso es `RootNotFound`, un 404 con su propio mensaje,
    y confundirlo con "no permitido" haría imposible distinguir un typo de un intento
    de escape.
    """
    if _looks_remote(raw):
        raise HTTPException(
            status_code=403, detail="Una ruta de red no puede ser la raíz de un proyecto."
        )

    # `resolve()` y no `absolute()`: sin seguir los symlinks, un link adentro de la
    # base que apunta afuera pasaría el `is_relative_to`.
    candidate = Path(raw).resolve()
    for base in allowed:
        if candidate.is_relative_to(base.resolve()):
            return candidate

    raise HTTPException(status_code=403, detail="La ruta está fuera de los directorios permitidos.")
