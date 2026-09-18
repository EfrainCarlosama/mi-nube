from __future__ import annotations

from enum import Flag, StrEnum, auto


class Capability(Flag):
    NONE = 0
    VIEW = auto()
    DOWNLOAD = auto()
    UPLOAD = auto()
    CREATE_FOLDER = auto()
    RENAME = auto()
    MODIFY = auto()
    MOVE = auto()
    DELETE = auto()


class PermissionLevel(StrEnum):
    NO_ACCESS = "Sin acceso"
    VIEW_ONLY = "Solo ver"
    VIEW_AND_DOWNLOAD = "Ver y descargar"
    UPLOAD = "Subir"
    MODIFY = "Modificar"
    FULL_CONTROL = "Control total"
    CUSTOM = "Personalizado"


class ProjectRole(StrEnum):
    OWNER = "Propietario general"
    PROJECT_ADMIN = "Administrador de proyecto"
    COLLABORATOR = "Colaborador"
    VIEWER = "Visualizador"


class GraphAccess(StrEnum):
    NONE = "none"
    READ = "read"
    WRITE = "write"


DEFAULT_CAPABILITIES: dict[PermissionLevel, Capability] = {
    PermissionLevel.NO_ACCESS: Capability.NONE,
    PermissionLevel.VIEW_ONLY: Capability.VIEW,
    PermissionLevel.VIEW_AND_DOWNLOAD: Capability.VIEW | Capability.DOWNLOAD,
    PermissionLevel.UPLOAD: Capability.VIEW | Capability.DOWNLOAD | Capability.UPLOAD,
    PermissionLevel.MODIFY: (
        Capability.VIEW
        | Capability.DOWNLOAD
        | Capability.UPLOAD
        | Capability.CREATE_FOLDER
        | Capability.RENAME
        | Capability.MODIFY
        | Capability.MOVE
    ),
    PermissionLevel.FULL_CONTROL: (
        Capability.VIEW
        | Capability.DOWNLOAD
        | Capability.UPLOAD
        | Capability.CREATE_FOLDER
        | Capability.RENAME
        | Capability.MODIFY
        | Capability.MOVE
        | Capability.DELETE
    ),
    PermissionLevel.CUSTOM: Capability.NONE,
}


def graph_access_for(level: PermissionLevel, capabilities: Capability | None = None) -> GraphAccess:
    effective = capabilities if level is PermissionLevel.CUSTOM else DEFAULT_CAPABILITIES[level]
    write_capabilities = (
        Capability.UPLOAD
        | Capability.CREATE_FOLDER
        | Capability.RENAME
        | Capability.MODIFY
        | Capability.MOVE
        | Capability.DELETE
    )
    if effective & write_capabilities:
        return GraphAccess.WRITE
    if effective & (Capability.VIEW | Capability.DOWNLOAD):
        return GraphAccess.READ
    return GraphAccess.NONE
