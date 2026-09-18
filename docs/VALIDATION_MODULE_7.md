# Validación del Módulo 7

**Fecha:** 17/09/2026  
**Modalidad:** OneDrive Personal

## Alcance compatible

Microsoft Graph Delta Query está disponible para cuentas Microsoft personales con permisos
delegados de archivos. Mi Nube conserva un cursor por unidad/proyecto y usa los permisos ya
concedidos `Files.ReadWrite`; no requiere permisos empresariales ni un tenant organizacional.

Delta devuelve el último estado del elemento, no cada operación intermedia. La identidad
`lastModifiedBy` se presenta como responsable de la última modificación disponible, pero no
se etiqueta como auditoría completa.

## Automatización

Las 43 pruebas verifican:

- línea base con `token=latest`;
- seguimiento de todas las páginas y confirmación del `deltaLink` final;
- conservación de la última aparición cuando Graph repite un elemento;
- restablecimiento de un cursor expirado;
- clasificación de creación y renombrado a partir del estado persistido;
- conciliación de una acción local con el cambio remoto equivalente;
- migración SQLite v4 y construcción de la interfaz actualizada.

## Validación real

Se creó un alcance temporal de proyecto en OneDrive Personal:

1. Se generaron líneas base independientes para el proyecto y la unidad.
2. Se creó `Carpeta inicial` y el siguiente Delta Query produjo el evento `creó`.
3. Se renovó el ETag vigente y se renombró a `Carpeta renombrada`.
4. El siguiente Delta Query produjo `renombró` y conservó el nuevo cursor.
5. El alcance remoto temporal fue enviado a la papelera.
6. La base SQLite temporal y sus archivos auxiliares fueron eliminados.

La base de producción quedó en la migración 4, con dos líneas base reales y cero eventos
históricos artificiales.
