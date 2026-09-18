# Mi Nube

Mi Nube es una aplicación de escritorio para Windows orientada a gestionar archivos
personales y proyectos de ingeniería/arquitectura en OneDrive. La versión `0.9.0` incluye
los módulos 1 a 9: autenticación segura, exploración y transferencias reales, proyectos,
permisos, actividad, flujo documental y distribución para Windows.

## Estado actual

- Ventana principal moderna construida con PySide6.
- Navegación lateral: Inicio, Personal, Trabajo, Recientes, Compartidos, Actividad y
  Configuración.
- Panel de inicio, explorador personal y catálogo de proyectos conectados a OneDrive.
- Configuración mediante variables de entorno y archivo `.env` local.
- Logging rotativo en el directorio de datos de la aplicación.
- Contrato desacoplado para la futura integración con Microsoft Graph.
- Inicio/cierre de sesión oficial mediante MSAL y navegador del sistema.
- Caché de sesión cifrada por usuario de Windows mediante DPAPI.
- Explorador paginado de archivos y carpetas de OneDrive Personal.
- Crear carpetas, subir/descargar archivos pequeños, renombrar, mover y eliminar.
- Búsqueda, metadatos, ordenamiento y cuota de almacenamiento.
- Reintentos y mensajes recuperables para fallos de Graph.
- Pruebas unitarias y de arranque de la interfaz.
- Instalador por usuario, canal HTTPS de actualización firmado y rollback de migraciones.

## Requisitos

- Windows 10/11.
- Python 3.11 o superior (solo durante desarrollo).

## Instalación para desarrollo

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

## Ejecución

```powershell
mi-nube
```

También puede ejecutarse sin el comando instalado:

```powershell
python -m mi_nube
```

## Pruebas y calidad

```powershell
python -m pytest
python -m ruff check .
```

Para una comprobación automática de arranque sin mostrar la ventana:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m mi_nube --smoke-test
```

## Configuración

Las variables soportadas en este módulo son:

| Variable | Valor inicial | Descripción |
|---|---|---|
| `MI_NUBE_ENV` | `development` | Entorno de ejecución. |
| `MI_NUBE_LOG_LEVEL` | `INFO` | Nivel de detalle de logs. |
| `MI_NUBE_DATA_DIR` | `%LOCALAPPDATA%\MiNube` | Directorio local de datos. |
| `MICROSOFT_CLIENT_ID` | vacío | Id. público del registro de aplicación. |
| `MICROSOFT_TENANT_ID` | `common` | Tenant específico o audiencia común. |
| `MI_NUBE_UPDATE_URL` | vacío | URL HTTPS del manifiesto de actualización firmado. |

Para registrar la aplicación y configurar estas variables consulte
[docs/AUTH_SETUP.md](docs/AUTH_SETUP.md). No deben guardarse contraseñas ni secretos de
cliente en el repositorio.

## Estructura

```text
src/mi_nube/
├── app/            # composición y configuración
├── auth/           # MSAL, controlador y caché protegida con DPAPI
├── domain/         # modelos y contratos del negocio
├── graph/          # cliente HTTP y controlador de OneDrive Personal
├── services/       # casos de uso y datos simulados
├── updates/        # manifiesto firmado, descarga y controlador de actualización
└── ui/             # ventana, componentes, tema y vistas
tests/              # pruebas automatizadas
docs/               # decisiones técnicas complementarias
```

Consulte [ARCHITECTURE.md](ARCHITECTURE.md) para el diseño técnico y
[ROADMAP.md](ROADMAP.md) para las fases planificadas.

## Instalador y publicación

El instalador generado está en `dist/MiNubeSetup.exe`. Se instala para el usuario actual,
sin solicitar privilegios de administrador. Al desinstalar, pregunta si también se deben
borrar la sesión, la configuración, las portadas y el historial local; la opción inicial
conserva esos datos.

Para compilar una versión reproducible de Windows:

```powershell
.\scripts\build_windows.ps1
```

El script genera la aplicación, prueba su arranque, crea el instalador y escribe hashes
SHA-256. Si existe un certificado de firma de código en el almacén de Windows, configure su
huella en `MI_NUBE_SIGN_CERT_SHA1` y ejecute con `-RequireSignature`. Consulte
[docs/PACKAGING.md](docs/PACKAGING.md) para el procedimiento completo y la publicación del
manifiesto de actualización.

## Uso de OneDrive Personal

1. Configure la aplicación de Entra según [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md).
2. Abra **Configuración** o **Personal** y pulse **Conectar OneDrive**.
3. Complete el consentimiento de Microsoft para `User.Read` y `Files.ReadWrite`.
4. En Personal, pulse **Actualizar** para cargar la raíz.

Los archivos de hasta 10 MiB usan carga directa. Los archivos mayores usan Upload Sessions
en bloques de 10 MiB, con progreso visible, cancelación y reintento automático del bloque
interrumpido. El límite por archivo es 250 GB, sujeto al espacio disponible en OneDrive.

## Cola de transferencias

Las subidas y descargas se añaden a una cola persistente y se procesan una por una para
reducir errores y límites de servicio. El botón **Transferencias** permite consultar el
estado, reanudar un trabajo pausado o fallido y descartar un trabajo.

- Las subidas grandes continúan desde el último fragmento confirmado por OneDrive.
- Las sesiones preautorizadas se cifran con Windows DPAPI antes de guardarse en SQLite.
- Las descargas incompletas conservan un archivo oculto `.part` y continúan mediante rangos.
- Al finalizar se comprueban tamaño y hash, y el destino se reemplaza de forma atómica.
- Si el archivo local o remoto cambió, la aplicación no mezcla versiones diferentes.

Al cerrar sesión, la transferencia activa se pausa. Al volver a iniciar sesión, los trabajos
que estaban en curso regresan a la cola y pueden continuar.

## Sincronización y actividad

La sección **Actividad** consulta los cambios incrementales de OneDrive Personal. Pulse
**Sincronizar ahora** para comprobarlos inmediatamente; con una sesión abierta, Mi Nube
también actualiza cada cinco minutos.

- Cada proyecto y la unidad personal mantienen un cursor independiente en SQLite.
- La primera ejecución crea una línea base y no muestra todo el contenido como actividad nueva.
- Las ejecuciones siguientes registran creaciones, subidas, modificaciones, movimientos,
  renombrados y eliminaciones.
- El filtro permite mostrar Personal, un proyecto concreto o todos los espacios.
- El origen indica **Mi Nube**, **OneDrive** o **Confirmado** cuando ambos registros coinciden.

Delta Query devuelve el estado final conocido de cada elemento, no todas las operaciones
intermedias. `lastModifiedBy` identifica la última identidad que modificó el elemento, pero
una cuenta personal no ofrece aquí un registro forense o de auditoría completo.

## Flujo documental de proyectos

Dentro de un proyecto, seleccione un archivo en **Archivos** y pulse **Estado y revisión**.
Puede asignar Borrador, En revisión, Aprobado u Obsoleto y una revisión como `R01`.

La nomenclatura es opcional. Al activarla se genera una vista previa como:

```text
ARQ-001-R01-Planta-Baja.pdf
EST-004-R03.dwg
PRE-001-R02-Presupuesto.xlsx
```

El nombre real de OneDrive solo cambia si se marca **Renombrar también el archivo real en
OneDrive**. El ETag evita reemplazar silenciosamente un cambio externo más reciente.

La pestaña **Documentos** permite buscar, filtrar por estado, revisar el historial y exportar
un reporte CSV UTF-8 compatible con Excel. SQLite guarda únicamente metadatos e historial;
el contenido de los documentos continúa en OneDrive.

## Proyectos de trabajo

La sección **Trabajo** guarda sus proyectos dentro de la carpeta `Mi Nube - Trabajo` de
OneDrive. Al crear un proyecto puede generar automáticamente la plantilla de ingeniería y
arquitectura. La plantilla se modifica desde **Configurar plantilla** usando dos espacios por
nivel de subcarpeta.

SQLite conserva únicamente metadatos, IDs remotos y versiones de plantilla en
`%LOCALAPPDATA%\MiNube\mi_nube.db`; los archivos permanecen en OneDrive. Si falla una parte
de la creación, la aplicación revierte la carpeta incompleta y no registra el proyecto.

Cada tarjeta de proyecto permite añadir o cambiar una foto de portada. La aplicación la
recorta automáticamente y guarda una copia local en
`%LOCALAPPDATA%\MiNube\project-covers`; la portada no se sube a OneDrive ni modifica los
archivos del proyecto.

El explorador identifica las carpetas mediante iconos de colores y omite la ruta en la tabla
para mantenerla despejada. La ruta completa continúa disponible al seleccionar un elemento y
pulsar **Información**.

## Equipo y permisos en OneDrive Personal

Cada proyecto incluye una pestaña **Equipo**. Desde allí el propietario puede agregar un
correo Microsoft, asignar un rol, editar políticas por carpeta, revocar accesos y consultar
el historial.

Por privacidad, los correos se utilizan únicamente de forma interna para autenticación,
invitaciones y permisos. La interfaz muestra solo el nombre registrado de cada persona; el
correo del propietario tampoco aparece en la barra lateral, Configuración, Equipo o historial.

OneDrive Personal solo aplica dos niveles reales: `read` y `write`. Mi Nube traduce y muestra
siempre el resultado:

- Solo ver y Ver/descargar → Lector (`read`).
- Subir, Modificar y Control total → Editor (`write`).
- Sin acceso → sin permiso directo.
- Personalizado → `read`, `write` o ninguno según las capacidades elegidas.

Los controles individuales de un permiso personalizado se aplican dentro de Mi Nube, pero
no pueden impedir acciones realizadas directamente desde la web de OneDrive. Consulte
[docs/PERMISSIONS_PERSONAL.md](docs/PERMISSIONS_PERSONAL.md).

## Licencia

Mi Nube se distribuye como software libre bajo la GNU General Public License versión 3.0
exclusivamente (`GPL-3.0-only`). Consulte [LICENSE](LICENSE) para leer las condiciones
completas.

Consulte también la [política de privacidad](PRIVACY.md), la [política de seguridad](SECURITY.md),
la [guía de contribuciones](CONTRIBUTING.md) y la [política de firma](CODE_SIGNING_POLICY.md).
