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


class NoKnownSources(PromptBriefError):
    """El directorio no tiene ninguna de las fuentes que PromptBrief sabe leer."""


class ProfileAlreadyExists(PromptBriefError):
    """Ya hay un perfil con ese nombre y no se pidió sobrescribirlo."""


class RootNotFound(PromptBriefError):
    """El directorio del proyecto no existe o no es un directorio.

    Hereda de PromptBriefError a propósito: para un consumidor HTTP esto es culpa
    del pedido (4xx), no una falla del servidor.
    """


class StoredProfileCorrupt(ProfileCorrupt):
    """El perfil guardado en disco está deformado.

    Se distingue de ProfileCorrupt porque el cliente no lo mandó ni puede arreglarlo
    reenviando otra cosa: es integridad de datos del servidor, y va a 500.
    """
