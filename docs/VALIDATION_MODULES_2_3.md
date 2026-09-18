# Validación real de los Módulos 2 y 3

**Fecha:** 17/09/2026  
**Entorno:** Windows, cuenta Microsoft personal, Microsoft Graph `v1.0`  
**Privacidad:** este documento omite correo, IDs, tokens y nombres de archivos del usuario.

## Módulo 2 — Autenticación

- Registro de aplicación configurado con autoridad `common`.
- Permisos delegados `User.Read` y `Files.ReadWrite`.
- Inicio interactivo completado mediante el navegador de Microsoft.
- Caché MSAL cifrada con Windows DPAPI creada correctamente.
- Cuenta restaurada desde la caché en una nueva instancia del servicio.
- Token de Graph adquirido silenciosamente sin interacción.
- Cierre de sesión real completado.
- Archivo de caché DPAPI eliminado al cerrar sesión.
- Una nueva instancia ya no restauró la cuenta después del cierre.

## Módulo 3 — OneDrive Personal

La prueba creó una carpeta temporal única en la raíz y ejecutó:

1. Listado de la raíz.
2. Consulta de cuota.
3. Búsqueda real.
4. Creación de carpeta y subcarpeta.
5. Subida de un archivo de texto pequeño.
6. Descarga y comparación SHA-256 del contenido.
7. Renombrado con ETag.
8. Consulta de metadatos.
9. Movimiento a la subcarpeta.
10. Verificación del contenido del destino.
11. Envío de la carpeta temporal completa a la papelera.

Todos los controles finalizaron correctamente. No se usó la carpeta sincronizada de
OneDrive de Windows y no se guardaron archivos remotos en SQLite.

## Módulo 3.1 — Cargas grandes

La ampliación usa Upload Sessions para archivos mayores de 10 MiB, bloques secuenciales de
10 MiB, progreso, cancelación y reintentos limitados. Las pruebas automatizadas verifican
fragmentación, continuidad después de un error transitorio, descarte de una sesión cancelada
y rechazo de URLs de carga no confiables.

**Validación real (17/09/2026):** se subió un archivo temporal de 25 MiB mediante tres
fragmentos confirmados al 40 %, 80 % y 100 %. El tamaño remoto coincidió exactamente con
26.214.400 bytes. La prueba también confirmó el host de Upload Session utilizado actualmente
por OneDrive Personal. La carpeta remota se envió a la papelera y el archivo local temporal
fue eliminado.

## Estado posterior

La sesión quedó cerrada deliberadamente como parte de la prueba. La siguiente ejecución de
Mi Nube debe mostrar la cuenta desconectada y solicitar autenticación al pulsar **Conectar
OneDrive**. Este comportamiento es el esperado.
