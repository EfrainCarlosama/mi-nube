# Roadmap de Mi Nube

El desarrollo se realizará por módulos cerrados y verificables. Un módulo no comienza
hasta que el anterior haya sido revisado y aprobado.

## Módulo 1 — Base del proyecto (completado)

- [x] Estructura modular con paquete `src`.
- [x] Configuración por entorno y rutas locales seguras.
- [x] Logging a consola y archivo rotativo.
- [x] Ventana principal PySide6 y navegación lateral.
- [x] Vistas iniciales para las siete secciones principales.
- [x] Tema visual consistente y componentes reutilizables.
- [x] Datos simulados de proyectos, actividad y almacenamiento.
- [x] Puerto abstracto preparado para Microsoft Graph.
- [x] Pruebas de dominio, configuración y arranque de UI.
- [x] Documentación inicial.

**Criterio de salida:** la aplicación arranca, permite recorrer todas las vistas sin red,
genera logs y supera las pruebas automatizadas. No contiene llamadas a Graph.

## Módulo 2 — Autenticación Microsoft (completado)

- [x] Documentar el registro de la aplicación en Microsoft Entra ID.
- [x] Implementar OAuth 2.0 Authorization Code con PKCE mediante MSAL.
- [x] Cifrar la caché de tokens con Windows DPAPI; nunca guardar contraseñas.
- [x] Añadir inicio/cierre de sesión y perfil del propietario.
- [x] Manejar expiración, cancelación, configuración ausente y errores de autenticación.
- [x] Pruebas con adaptadores simulados sin usar una cuenta real.

**Criterio de salida:** con un `MICROSOFT_CLIENT_ID` válido, la aplicación inicia sesión en
el navegador oficial, restaura la cuenta desde una caché cifrada y permite cerrar la sesión
local. Solo solicita `User.Read`; todavía no accede a OneDrive.

**Validación real (17/09/2026):** inicio interactivo, restauración desde DPAPI, adquisición
silenciosa de token y cierre de sesión comprobados. El cierre eliminó la caché local.

## Módulo 3 — Explorador OneDrive Personal (completado)

- [x] Listado paginado de carpetas y archivos con Microsoft Graph.
- [x] Navegación por carpetas, búsqueda global y ordenamiento por columnas.
- [x] Crear carpetas, subir y descargar archivos.
- [x] Renombrar, mover, enviar a la papelera y mostrar metadatos.
- [x] Mostrar cuota de almacenamiento.
- [x] Errores tipados para red, 401, 403, 404, 409/412, 429 y 5xx.
- [x] Reintentos limitados respetando `Retry-After` y backoff.
- [x] Operaciones de red fuera del hilo de la interfaz.

**Criterio de salida:** con una cuenta configurada, Personal trabaja directamente contra
Microsoft Graph sin depender de la carpeta local de OneDrive. Las pruebas usan un transporte
HTTP simulado; la validación con una cuenta real requiere el Client ID del propietario.

**Validación real (17/09/2026):** listado paginado, cuota, búsqueda, creación de carpeta y
subcarpeta, subida, descarga con verificación de contenido, metadatos, renombrado, movimiento
y envío a la papelera completados correctamente. No quedaron elementos de prueba activos.

## Módulo 3.1 — Cargas grandes (completado)

- [x] Carga directa hasta 10 MiB.
- [x] Upload Sessions para archivos mayores, hasta el límite de 250 GB de OneDrive.
- [x] Fragmentos secuenciales de 10 MiB sin cargar el archivo completo en memoria.
- [x] Progreso visible y cancelación desde la vista Personal.
- [x] Reintento del fragmento actual ante red inestable, `429` y errores `5xx`.
- [x] Validación estricta de la URL preautorizada y envío sin token OAuth.
- [x] Pruebas simuladas de fragmentación, reintento, cancelación y URL no confiable.
- [x] Validación real de tres fragmentos y tamaño remoto exacto en OneDrive Personal.

**Criterio de salida:** un archivo grande se transfiere en segundo plano conservando los
fragmentos ya aceptados mientras la sesión permanezca activa. La cola persistente y la
recuperación después de cerrar la aplicación siguen reservadas al Módulo 6.

## Módulo 4 — Proyectos y plantilla de carpetas (implementado)

- [x] Crear proyectos en `Mi Nube - Trabajo` con estructura base configurable.
- [x] Editar y versionar la plantilla predeterminada.
- [x] Buscar proyectos por nombre o cliente.
- [x] Abrir cada proyecto con el explorador real de OneDrive.
- [x] Persistir proyecto, plantilla e IDs remotos de carpetas en SQLite.
- [x] Aplicar migraciones, claves foráneas y transacciones locales.
- [x] Revertir la carpeta remota ante fallos parciales.
- [x] Mostrar progreso durante la creación del árbol.

**Criterio de salida:** la aplicación crea el árbol remoto sin bloquear la interfaz, registra
sus metadatos en una transacción local y puede abrir la raíz del proyecto para administrar
archivos.

**Validación real (17/09/2026):** proyecto temporal completo creado en OneDrive con 9
carpetas principales y 50 carpetas totales. Se comprobaron los registros SQLite y las seis
subcarpetas de `02 Estructuras`. El proyecto temporal fue enviado a la papelera.

## Módulo 5 — Usuarios, roles y permisos (implementado para OneDrive Personal)

- [x] Invitación por correo mediante Microsoft Graph.
- [x] Roles Propietario, Administrador de proyecto, Colaborador y Visualizador.
- [x] Acceso real `read` o `write` al proyecto completo o por carpeta.
- [x] Matriz jerárquica con los siete niveles internos y modo Personalizado.
- [x] Herencia visible y opción Aplicar a nuevas subcarpetas.
- [x] Revocación de todos los permisos directos al retirar un integrante.
- [x] Historial local auditable con usuario, carpeta, antes/después, fecha y administrador.
- [x] Migración SQLite v2 sin recrear la base.
- [x] Diferenciación visible entre política interna y acceso real de Graph.

**Criterio de salida:** la UI administra integrantes sin guardar contraseñas, Graph aplica
los accesos reales compatibles con OneDrive Personal y SQLite conserva reglas e historial.
La API real de lectura de permisos quedó validada; la prueba de invitación/revocación con un
tercero requiere un correo Microsoft de prueba proporcionado por el propietario.

## Módulo 6 — Transferencias grandes (completado)

- [x] Cola SQLite persistente con varias transferencias y una ejecución secuencial.
- [x] Pausa, reintento, cancelación y panel de estado en Personal y Trabajo.
- [x] Sesiones de subida recuperables y URL preautorizada cifrada con Windows DPAPI.
- [x] Recuperación automática de trabajos interrumpidos después de reiniciar la aplicación.
- [x] Descargas por rangos a un archivo `.part` estable y renovación del enlace temporal.
- [x] Verificación de tamaño y QuickXorHash; SHA-1 como alternativa si Graph lo entrega.
- [x] Reinicio seguro si el archivo local cambia, la sesión expira o cambia el ETag remoto.
- [x] Pruebas simuladas y validación completa contra OneDrive Personal real.

**Criterio de salida:** cerrar o perder la conexión no obliga a reiniciar una transferencia
grande desde cero mientras la sesión remota siga vigente. La cola conserva su estado sin
guardar archivos completos en SQLite ni exponer enlaces preautorizados.

**Validación real (17/09/2026):** una subida de 25 MiB se pausó a 10 MiB, se reconstruyó el
servicio y continuó hasta el tamaño remoto exacto. La descarga del mismo archivo se pausó
aproximadamente a 5 MiB, se reanudó mediante `Range` y superó la comprobación QuickXorHash.
La carpeta temporal remota fue enviada a la papelera y los archivos locales se eliminaron.

## Módulo 7 — Sincronización y actividad (completado para OneDrive Personal)

- [x] Delta Query independiente para la unidad personal y cada proyecto registrado.
- [x] Cursores persistentes y paginación completa sin volver a recorrer toda la unidad.
- [x] Línea base inicial con `token=latest`, sin inventar actividad histórica.
- [x] Sincronización manual y automática cada cinco minutos mientras exista una sesión.
- [x] Recuperación segura cuando Graph invalida un cursor y solicita resincronización.
- [x] Clasificación de creación, subida, modificación, renombrado, movimiento y eliminación.
- [x] Registro local de acciones hechas desde Mi Nube y conciliación con el cambio remoto.
- [x] Pantalla de actividad real con búsqueda, filtro por proyecto y origen del evento.
- [x] Migración SQLite v4 para alcances, cursores, estado mínimo y eventos.

**Criterio de salida:** después de crear una línea base, cada ejecución solicita únicamente
los cambios pendientes de cada alcance, actualiza su cursor solo al terminar todas las páginas
y conserva actividad útil sin presentar Delta Query como un registro de auditoría completo.

**Validación real (17/09/2026):** se creó un alcance temporal de proyecto, se inicializaron
los cursores de proyecto y unidad, y los ciclos siguientes detectaron la creación y el
renombrado de una carpeta. El cursor quedó persistido, la carpeta remota se envió a la
papelera y la base temporal se eliminó. La base real quedó migrada y con sus líneas base.

## Módulo 8 — Flujo documental (completado)

- [x] Estados internos Borrador, En revisión, Aprobado y Obsoleto.
- [x] Revisión normalizada con formato `R01`, `R02`, etc.
- [x] Nomenclatura opcional por disciplina, número, revisión y título.
- [x] Vista previa antes de modificar el nombre remoto.
- [x] Renombrado opcional en OneDrive protegido con ETag.
- [x] Historial de estado, revisión, nombre, fecha y responsable.
- [x] Columna Estado y editor desde el explorador del proyecto.
- [x] Pestaña Documentos con búsqueda y filtro por estado.
- [x] Resumen por estado y exportación de reporte CSV compatible con Excel.
- [x] Migración SQLite v5 sin guardar contenido de archivos.

**Criterio de salida:** un archivo real de proyecto puede vincularse a metadatos internos,
cambiar de estado y revisión, aplicar opcionalmente un nombre normalizado y conservar un
historial auditable. No se renombra OneDrive sin una selección explícita del propietario.

**Validación real (17/09/2026):** un PDF temporal conservó su nombre como Borrador R01 y
después fue aprobado como R02 con el nombre remoto `ARQ-001-R02-Planta-Baja.pdf`. Se
verificaron dos entradas de historial, el resumen y el CSV. La carpeta remota se envió a la
papelera y los datos locales temporales se eliminaron.

## Módulo 9 — Empaquetado, instalador y actualización (implementado)

- [x] Build reproducible y autocontenido con PyInstaller.
- [x] Instalador por usuario `MiNubeSetup.exe` y desinstalación con conservación opcional de datos.
- [x] Integración de firma Authenticode para la aplicación y el instalador.
- [ ] Adjuntar un certificado Authenticode público antes de distribuir a terceros.
- [x] Canal de actualización exclusivamente HTTPS con manifiesto firmado mediante Ed25519.
- [x] Descarga en streaming y validación estricta de versión, tamaño y SHA-256.
- [x] Copia previa y rollback automático si falla una migración SQLite.
- [x] Pruebas automatizadas, arranque empaquetado y ciclo real de instalación/desinstalación.

**Criterio de salida:** la misma fuente produce el mismo ejecutable, el instalador funciona
sin privilegios de administrador, una actualización alterada es rechazada y una migración
fallida restaura la base anterior.

**Validación (18/09/2026):** dos compilaciones consecutivas produjeron el mismo SHA-256 de
`MiNube.exe`. El instalador completó instalación, arranque y desinstalación con código 0; el
manifiesto de prueba superó la verificación Ed25519 y la suite validó rollback SQLite. El
artefacto actual permanece sin Authenticode porque todavía no se ha suministrado un
certificado de firma de código; por ello es apto para prueba local, no para publicación final.
