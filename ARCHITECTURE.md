# Arquitectura de Mi Nube

## 1. Alcance y principios

Mi Nube es un cliente de escritorio: se comunica directamente con Microsoft Graph y no
depende de la carpeta sincronizada por OneDrive ni convierte una PC en servidor. El diseño
aplica separación por capas, inversión de dependencias y adaptadores reemplazables. La UI
no conoce HTTP, tokens ni SQL; consume servicios de aplicación mediante contratos.

Principios:

1. Seguridad por diseño: OAuth/MSAL, mínimo privilegio y secretos fuera del código.
2. Dominio independiente: modelos y reglas sin dependencias de PySide6 o Graph.
3. Operaciones remotas tolerantes a fallos: resultados explícitos, reintentos limitados y
   nunca cerrar la UI por una excepción HTTP.
4. Base local como caché y metadatos propios, no como copia de archivos.
5. Desarrollo incremental: cada módulo tiene pruebas y criterio de salida.

## 2. Capas

```text
┌─────────────────────────────────────────────────────────┐
│ UI (PySide6): ventanas, vistas, widgets, view models     │
├─────────────────────────────────────────────────────────┤
│ Aplicación: casos de uso, coordinación y políticas      │
├──────────────────────┬──────────────────────────────────┤
│ Dominio: modelos,    │ Puertos: Drive, Auth, Repositorio│
│ permisos y reglas    │ Transferencias, Actualizaciones  │
├──────────────────────┴──────────────────────────────────┤
│ Adaptadores: Microsoft Graph/MSAL, SQLite, HTTP, Windows│
└─────────────────────────────────────────────────────────┘
```

`MockDataService` todavía alimenta Inicio y Actividad. Personal consume el puerto
`GraphDriveClient`, implementado por `HttpGraphDriveClient`. Trabajo usa `ProjectService`,
`ProjectController` y `SqliteProjectRepository`; ningún widget realiza llamadas HTTP o SQL
directamente.

## 3. Estructura propuesta

```text
src/mi_nube/
├── app/
│   ├── bootstrap.py       # composición de dependencias
│   ├── logging_config.py  # logging rotativo
│   └── settings.py        # variables y rutas
├── auth/
│   ├── controller.py      # puente asíncrono entre UI y autenticación
│   ├── msal_service.py    # cliente público MSAL y consentimiento
│   └── token_cache.py     # persistencia cifrada con Windows DPAPI
├── domain/
│   ├── models.py          # entidades inmutables
│   └── permissions.py     # niveles y capacidades
├── graph/
│   ├── controller.py      # trabajos de red asíncronos y señales para la UI
│   ├── errors.py          # errores tipados y recuperables
│   ├── http_client.py     # adaptador Microsoft Graph v1.0
│   └── ports.py           # contrato del explorador OneDrive
├── database/
│   └── sqlite.py          # conexión, versión de esquema y migraciones
├── repositories/
│   ├── project_repository.py # proyectos, carpetas y plantillas en SQLite
│   └── transfer_repository.py # cola, progreso y sesiones cifradas
├── projects/
│   └── controller.py      # trabajos asíncronos para la vista Trabajo
├── transfers/
│   └── controller.py      # ejecución secuencial y señales de progreso
├── sync/
│   └── controller.py      # sincronización periódica fuera del hilo de UI
├── documents/
│   ├── controller.py      # operaciones documentales asíncronas
│   └── errors.py          # validaciones visibles y recuperables
├── services/
│   ├── transfer_service.py # pausa, recuperación e integridad
│   ├── sync_service.py    # Delta Query, clasificación y conciliación
│   ├── document_service.py # estados, revisión, nombres y reportes
│   ├── integrity.py       # QuickXorHash y SHA-1 por streaming
│   └── mock_data.py       # datos de demostración del Módulo 1
└── ui/
    ├── components/        # widgets reutilizables
    ├── views/             # una vista por contexto funcional
    ├── main_window.py
    └── theme.py
```

En módulos siguientes se agregará `updates/` solo cuando tenga
implementación real. Evitamos directorios vacíos que aparenten capacidades inexistentes.

## 4. Modelos principales

| Modelo | Responsabilidad |
|---|---|
| `AccountProfile` | Identidad autenticada, rol global y tenant. |
| `DriveItem` | Archivo o carpeta remota y metadatos de Graph. |
| `Project` | Proyecto local vinculado al ID de su carpeta raíz en OneDrive. |
| `ProjectFolder` | Relación estable entre ruta de plantilla e ID remoto. |
| `ProjectTemplate` | Árbol versionado usado al crear proyectos nuevos. |
| `ProjectMember` | Integrante y rol general dentro de un proyecto. |
| `FolderPermissionRule` | Política interna y permiso Graph directo de una carpeta. |
| `PermissionChange` | Registro inmutable del antes/después de un acceso. |
| `ProjectMember` | Vínculo entre usuario, proyecto y rol. |
| `PermissionRule` | Capacidades concedidas o negadas sobre una carpeta. |
| `PermissionChange` | Evento auditable antes/después. |
| `TransferJob` | Subida/descarga, progreso, reintento y sesión reanudable. |
| `SyncCursor` | Delta token y última sincronización por alcance. |
| `ActivityEvent` | Acción, actor, elemento, fecha y proyecto. |
| `DocumentMetadata` | Estado, revisión y nomenclatura propia. |

Los modelos de proyectos se incorporaron con el Módulo 4 y se almacenan mediante migraciones
SQLite. Los modelos de permisos, actividad y sincronización se incorporarán con sus módulos.

## 5. Dependencias

### Actuales

- Python 3.11+: lenguaje y biblioteca estándar.
- PySide6: interfaz nativa multiplataforma, con destino principal Windows.
- python-dotenv: configuración local de desarrollo sin hardcodear valores.
- pytest y Ruff (desarrollo): pruebas y análisis estático.

### Distribución y seguridad de versiones

- PyInstaller: aplicación autocontenida en formato `onedir`.
- Inno Setup: instalador y desinstalador por usuario, sin elevación administrativa.
- `cryptography`: verificación Ed25519 del manifiesto de actualización.
- `packaging`: comparación normalizada de versiones antes de ofrecer una descarga.
- SignTool/Authenticode: firma opcional pero obligatoria para una publicación final.

## 6. Dependencias de Microsoft Graph

| Capacidad | Endpoint/concepto Graph previsto |
|---|---|
| Identidad y perfil | MSAL + `GET /me` |
| Archivos y carpetas | Drive/DriveItem children, content y search |
| Operaciones | create folder, move, rename, delete |
| Cuota | Drive `quota` |
| Archivos grandes | `createUploadSession` y rangos de bytes |
| Cambios incrementales | DriveItem `delta` |
| Compartición | invitations, permissions y sharing links |
| Actividad/auditoría | disponibilidad según licencia y APIs; requiere validación |

Los permisos internos de la aplicación y los permisos efectivos de OneDrive no son
equivalentes automáticamente. Antes del Módulo 5 se decidirá si cada proyecto vive en el
OneDrive del propietario, un SharePoint Site/Document Library o una unidad compartida.
Esa decisión condiciona colaboración, revocación, auditoría y continuidad operativa.

### Cliente Graph del Módulo 3

- API estable `v1.0` y permiso delegado `Files.ReadWrite`.
- Paginación completa mediante enlaces `@odata.nextLink` validados.
- Carga directa hasta 10 MiB y Upload Sessions en bloques de 10 MiB para archivos mayores.
- Progreso y cancelación en segundo plano; reintento limitado conserva los bloques aceptados.
- Límite de 250 GB por archivo con conflicto en modo `fail`.
- Descargas reanudables por rangos a `.part`, verificación de hash y reemplazo atómico.
- ETags (`If-Match`) en renombrado y eliminación para detectar cambios concurrentes.
- Reintento de 429/5xx con `Retry-After` o backoff exponencial limitado.
- No se guardan access tokens en modelos, logs ni widgets.

### Cola persistente del Módulo 6

- SQLite conserva únicamente metadatos, estados y progreso; nunca el contenido del archivo.
- Solo una transferencia se ejecuta a la vez y las demás permanecen en cola.
- Una subida guarda su `uploadUrl` cifrada con DPAPI y consulta `nextExpectedRanges` al volver.
- Una descarga renueva siempre `@microsoft.graph.downloadUrl`, que es temporal y no se guarda.
- La respuesta parcial se solicita al enlace preautorizado sin enviar el token OAuth.
- QuickXorHash, disponible en OneDrive Personal, valida el contenido antes del reemplazo final.

### Sincronización incremental del Módulo 7

- `sync_scopes` conserva un `deltaLink` distinto para Personal y cada proyecto.
- La línea base usa `token=latest`; no enumera el pasado como si fueran eventos nuevos.
- Cada ciclo sigue `nextLink` hasta recibir el nuevo `deltaLink` y solo entonces lo confirma.
- `synced_items` conserva el estado mínimo necesario para distinguir renombrados y movimientos.
- `activity_events` combina cambios Graph con acciones locales y evita duplicados deterministas.
- Si Graph responde que el cursor expiró, se descarta el estado del alcance y se crea otra línea
  base segura en vez de aplicar un conjunto parcial.

### Flujo documental del Módulo 8

- `document_metadata` vincula el ID estable de Graph con estado, revisión y nomenclatura.
- `document_history` registra cada guardado con valores anteriores/nuevos y responsable.
- Los estados son propios de Mi Nube; no se presentan como columnas nativas de OneDrive.
- La nomenclatura se valida localmente y solo llama a Graph si el usuario solicita renombrar.
- El renombrado usa el ETag visible en el explorador para detectar modificaciones externas.
- Los reportes se generan desde SQLite y no necesitan descargar el contenido remoto.

## 7. Seguridad

- Flujo interactivo OAuth con navegador del sistema y PKCE; nunca contraseña embebida.
- Aplicación pública de escritorio sin client secret distribuido.
- Scopes delegados mínimos, consentimiento claro y revocable.
- Caché MSAL cifrada con DPAPI o almacén seguro de Windows.
- `.env` solo para identificadores/configuración de desarrollo, excluido de Git.
- Logs sin access tokens, URLs preautorizadas ni datos sensibles.
- Validación de rutas, nombres, tamaño y respuesta antes de escribir en disco.

## 8. Errores y resiliencia

El adaptador Graph traducirá HTTP a excepciones tipadas: autenticación, prohibido, no
encontrado, conflicto, límite de solicitudes, servicio no disponible y red. La capa de
aplicación decidirá si reautenticar, refrescar, reintentar con `Retry-After`, mostrar una
acción al usuario o abandonar. Las transferencias serán persistentes e idempotentes.

## 9. Persistencia y sincronización

SQLite guarda proyectos, IDs remotos de carpetas, plantillas versionadas y trabajos de
transferencia. El esquema usa una tabla `schema_migrations`, claves foráneas y transacciones.
En fases posteriores incorporará preferencias. Los archivos completos
permanecen en OneDrive, en destinos explícitos de descarga o temporalmente en `.part`.

Desde el Módulo 7 también guarda cursores Delta, una instantánea mínima por alcance y eventos
de actividad. Los enlaces Delta requieren el token OAuth normal y nunca se escriben en logs.

Desde el Módulo 8 guarda metadatos e historial documental. El borrado del proyecto elimina
estos registros mediante claves foráneas; el archivo remoto conserva su ciclo de vida normal.

Desde el Módulo 5 también guarda integrantes, reglas por carpeta y cambios de permisos. El
ID de cada permiso Graph se conserva para poder revocarlo de forma dirigida. El historial no
depende de que el integrante continúe activo.

La creación de un proyecto es una operación compensable: primero crea la raíz y el árbol en
OneDrive, después confirma todos los metadatos en una sola transacción SQLite. Ante un fallo,
envía la raíz remota incompleta a la papelera y no conserva un registro local parcial.

### Permisos con cuenta personal

`PermissionService` traduce las políticas internas al único modelo real disponible en
OneDrive Personal: `read`, `write` o ausencia de permiso directo. El propietario administra
invitaciones mediante Graph; SQLite nunca reemplaza el control de acceso remoto. Las
restricciones más finas son controles de la interfaz y se presentan como tales.

## 10. Riesgos técnicos principales

1. **Modelo de colaboración:** OneDrive personal no ofrece el mismo gobierno que una
   biblioteca de SharePoint. Debe validarse contra la licencia Microsoft 365 disponible.
2. **Permisos granulares:** la herencia/excepciones deseadas pueden requerir permisos de
   SharePoint o una capa propia; deben evitarse discrepancias entre UI y acceso real.
3. **Actividad del actor:** Graph Drive no siempre expone un historial completo con el
   nivel de detalle deseado; los audit logs pueden necesitar licencia/permisos adicionales.
4. **Archivos de ingeniería grandes:** sesiones expiran, las redes fallan y algunos formatos
   superan varios GB; se requieren chunks, persistencia, hashes y límites probados.
5. **Concurrencia/conflictos:** renombrados, borrados y ediciones externas exigen ETags y
   políticas explícitas de conflicto.
6. **Rate limits:** `429` y respuestas transitorias necesitan backoff y caché; no se debe
   refrescar toda la unidad.
7. **Distribución segura:** firma del ejecutable/instalador y del manifiesto de actualización
   para reducir alertas de Windows y ataques de sustitución.
8. **Rutas Windows:** nombres inválidos, rutas largas y archivos bloqueados requieren
   normalización y mensajes recuperables.

## 11. Empaquetado y actualizaciones

El Módulo 9 genera una carpeta autocontenida con PyInstaller y la encapsula en un instalador
Inno Setup por usuario. El build fija las variables que afectan el resultado, evita incluir
DLL ajenas procedentes del entorno del desarrollador y prueba el arranque del ejecutable
antes de producir el instalador. La firma Authenticode se aplica cuando el almacén de Windows
contiene el certificado indicado por `MI_NUBE_SIGN_CERT_SHA1`.

La UI consulta en segundo plano el manifiesto definido por `MI_NUBE_UPDATE_URL`. Tanto el
manifiesto como el instalador deben usar HTTPS. El manifiesto se verifica con una clave
Ed25519 incluida en la aplicación antes de comparar la versión; la descarga se acepta solo
si coincide exactamente con el tamaño y SHA-256 firmados. Después de la confirmación de la
persona, Mi Nube inicia el instalador y cierra la aplicación.

Antes de aplicar migraciones pendientes, SQLite crea una copia consistente mediante su API
de backup. Si una migración falla, restaura automáticamente esa copia y conserva el archivo
de respaldo para diagnóstico. Solo se retienen las tres copias más recientes.
