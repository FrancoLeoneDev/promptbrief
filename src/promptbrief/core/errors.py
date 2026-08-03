from __future__ import annotations


class PromptBriefError(Exception):
    """Base de todo error causado por el input, no por un bug interno.

    Un consumidor HTTP puede mapear esta jerarquía completa a 4xx y dejar que
    cualquier otra excepción caiga a 500, que es el comportamiento seguro.
    """


class EmptyRequestError(PromptBriefError):
    """No se puede armar un brief sin una descripción de la tarea."""


class InvalidProfileName(PromptBriefError):
    """El nombre de perfil no sirve como nombre de archivo de forma segura."""


class ProfileNotFound(PromptBriefError):
    """No existe un perfil con ese nombre."""


class ProfileCorrupt(PromptBriefError):
    """El YAML del perfil existe pero no tiene la forma esperada."""
