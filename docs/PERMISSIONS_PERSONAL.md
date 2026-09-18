# Permisos compatibles con OneDrive Personal

## Dos capas de autorización

Mi Nube muestra por separado:

1. **Política interna:** botones y operaciones habilitadas dentro de la aplicación.
2. **Acceso real:** permiso que Microsoft Graph aplica al archivo o carpeta en OneDrive.

SQLite conserva la política y el identificador del permiso remoto. Microsoft Graph sigue
siendo la autoridad efectiva; borrar la base local no revoca por sí solo un acceso remoto.

## Traducción

| Política de Mi Nube | Capacidades internas | Acceso real OneDrive |
|---|---|---|
| Sin acceso | Ninguna | Ningún permiso directo |
| Solo ver | Visualizar | `read` |
| Ver y descargar | Visualizar, descargar | `read` |
| Subir | Visualizar, descargar, subir | `write` |
| Modificar | Crear, editar, renombrar y mover | `write` |
| Control total | Incluye eliminar | `write` |
| Personalizado | Selección individual | `read`, `write` o ninguno |

Con `read`, OneDrive Personal también permite descargar. Con `write`, el usuario puede
realizar operaciones amplias desde OneDrive web, aunque Mi Nube oculte algún botón.

## Roles

- **Propietario general:** cuenta autenticada; no se guarda como invitado ni puede revocarse.
- **Administrador de proyecto:** `write` en la raíz del proyecto.
- **Visualizador:** `read` en la raíz del proyecto.
- **Colaborador:** sin acceso inicial a la raíz; recibe invitaciones directas en las carpetas
  que el propietario configure.

## Herencia y excepciones

Un permiso concedido en una carpeta alcanza a sus descendientes en OneDrive. Mi Nube marca
las reglas heredadas y permite registrar excepciones internas. Sin embargo, una excepción
`Sin acceso` en una subcarpeta no puede retirar un acceso que OneDrive ya heredó desde una
carpeta superior. Para aislamiento real, el propietario debe compartir únicamente las
carpetas específicas y no su antecesora.

La opción **Nuevas subcarpetas** queda almacenada para que la política interna continúe en
carpetas creadas posteriormente; la herencia real de OneDrive se aplica automáticamente.

## Invitación y revocación

- Administradores y visualizadores reciben una invitación al proyecto completo al agregarlos.
- Colaboradores reciben una invitación cuando se guarda una carpeta con `read` o `write`.
- Cambiar entre `read` y `write` revoca el permiso directo anterior y crea el nuevo.
- Quitar un integrante revoca todos los IDs de permiso directo registrados antes de eliminar
  su membresía local.

## Limitaciones conocidas

- Bloquear descarga y crear enlaces de solo subida no están disponibles para este escenario
  con OneDrive Personal.
- La cuenta invitada debe poder autenticarse con Microsoft para usar el acceso restringido.
- Los permisos creados fuera de Mi Nube se pueden consultar, pero no se asocian automáticamente
  con reglas locales en esta versión.
- Un modelo empresarial con denegaciones, grupos y gobierno central requeriría SharePoint o
  Microsoft 365 Business.

## Referencias oficiales

- [Invitar usuarios a un DriveItem](https://learn.microsoft.com/en-us/graph/api/driveitem-invite?view=graph-rest-1.0)
- [Listar permisos de un DriveItem](https://learn.microsoft.com/en-us/graph/api/driveitem-list-permissions?view=graph-rest-1.0)
- [Revocar acceso a un elemento](https://learn.microsoft.com/en-us/graph/api/permission-delete?view=graph-rest-1.0)
- [Compartir archivos y carpetas en OneDrive](https://support.microsoft.com/en-us/onedrive/share-files-and-folders-in-microsoft-onedrive)
