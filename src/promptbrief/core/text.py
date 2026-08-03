from __future__ import annotations

import re
import unicodedata

_TERM = re.compile(r"[a-z0-9]{3,}")

# Patrones de credencial. El grupo 1, cuando existe, es la parte que se conserva:
# "API_KEY=" sigue siendo información útil una vez tapado el valor.
_SECRETS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"
    ),
    # Credenciales embebidas en una URL de conexión: postgres://user:pass@host
    re.compile(r"(\b\w+://[^\s:/@]+:)[^\s@]{6,}@"),
    re.compile(
        r"((?i:api[_-]?key|secret|token|password|passwd)\s*[:=]\s*)"
        r"['\"]?[A-Za-z0-9_\-/+=]{16,}['\"]?"
    ),
)


def strip_accents(text: str) -> str:
    """Quita tildes para que 'sección' y 'seccion' se traten como la misma palabra."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def terms(text: str) -> set[str]:
    """Tokeniza para comparar relevancia, ignorando tildes y mayúsculas."""
    return set(_TERM.findall(strip_accents(text.lower())))


def _mask(match: re.Match[str]) -> str:
    return f"{match.group(1)}[REDACTED]" if match.groups() else "[REDACTED]"


def redact_secrets(text: str) -> tuple[str, bool]:
    """Reemplaza credenciales por [REDACTED]. Devuelve (texto, se_encontró_algo)."""
    redacted = text
    for pattern in _SECRETS:
        redacted = pattern.sub(_mask, redacted)
    return redacted, redacted != text
