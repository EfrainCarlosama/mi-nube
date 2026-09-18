# Decisiones técnicas

## ADR-001 — Arquitectura por capas

**Estado:** aceptada. La UI depende de servicios y contratos, nunca directamente de Graph o
SQLite. Esto permite probar el comportamiento con dobles y cambiar infraestructura.

## ADR-002 — Datos simulados en el Módulo 1

**Estado:** aceptada. No se solicita configuración de Entra ID ni cuenta Microsoft. Los datos
locales demuestran navegación y diseño, y serán sustituidos a través de servicios.

## ADR-003 — Paquete `src` y `pyproject.toml`

**Estado:** aceptada. El layout evita imports accidentales desde el directorio de trabajo y
centraliza dependencias, metadatos, pruebas y lint.

## ADR-004 — SQLite estándar con migraciones propias

**Estado:** aceptada. El alcance actual no necesita un ORM. Cada operación abre una conexión
corta, activa claves foráneas y usa transacciones. `schema_migrations` permite evolucionar el
modelo sin recrear la base local.

## ADR-005 — Proyectos en el OneDrive del propietario

**Estado:** aceptada para el Módulo 4. Los proyectos viven bajo `Mi Nube - Trabajo` y SQLite
solo conserva IDs y metadatos. Antes del Módulo 5 se debe validar si la colaboración final
continuará mediante OneDrive Personal compartido o requerirá una biblioteca de SharePoint.

## ADR-006 — Permisos compatibles con OneDrive Personal

**Estado:** aceptada. Graph es la autoridad para conceder y revocar acceso real. OneDrive
Personal expone `read` y `write`; los niveles adicionales son políticas internas que controlan
Mi Nube, no garantías contra acciones realizadas desde OneDrive web. La UI debe mostrar ambas
capas y nunca presentar una restricción interna como seguridad remota.

## Decisiones pendientes

- Posible migración futura de OneDrive Personal a SharePoint para gobierno empresarial.
- Política de cuentas invitadas que no tengan un correo Microsoft.
- Proveedor, firma y canal de actualizaciones.
