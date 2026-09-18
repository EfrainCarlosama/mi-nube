# Validación del Módulo 8

**Fecha:** 17/09/2026  
**Modalidad:** OneDrive Personal

## Implementación verificada

- estados Borrador, En revisión, Aprobado y Obsoleto;
- revisiones normalizadas desde entradas como `1`, `r1` o `R01`;
- nomenclatura opcional `DISCIPLINA-NÚMERO-REVISIÓN-TÍTULO.ext`;
- limpieza de caracteres incompatibles con nombres de Windows/OneDrive;
- renombrado remoto únicamente por selección explícita y con ETag;
- historial de estado, revisión, nombre y responsable;
- búsqueda y filtros por proyecto;
- conteo por estado y exportación CSV UTF-8 con BOM para Excel;
- migración SQLite v5 sin almacenar el contenido del archivo.

## Automatización

Las 50 pruebas verifican el flujo previo y además:

- que la nomenclatura permanezca desactivada de manera predeterminada;
- normalización `arq`, `4`, `2` → `ARQ-004-R02`;
- rechazo de revisiones inválidas y carpetas;
- renombrado Graph con el ETag original;
- dos entradas de historial al cambiar Borrador → Aprobado;
- filtros, conteos y contenido del reporte CSV.

## Validación real

Se creó una carpeta temporal y se subió `plano temporal.pdf`:

1. Se guardó como **Borrador**, revisión `R01`, sin nomenclatura; OneDrive conservó el nombre.
2. Se actualizó como **Aprobado**, revisión `R02`, disciplina `ARQ`, número `001`.
3. Con el renombrado explícito, Graph confirmó `ARQ-001-R02-Planta-Baja.pdf`.
4. SQLite conservó las dos entradas del historial.
5. El reporte contó un aprobado y el CSV incluyó estado, revisión y responsable.

La carpeta remota fue enviada a la papelera y la carpeta local temporal fue eliminada. La
base real quedó migrada a la versión 5, sin documentos artificiales.
