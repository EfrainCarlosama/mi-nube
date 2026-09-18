# Explorador OneDrive Personal

## Alcance del Módulo 3

La vista Personal se comunica por Internet con Microsoft Graph `v1.0`. No lee la carpeta
sincronizada por OneDrive de Windows y no almacena archivos completos en SQLite.

Operaciones implementadas:

- listar raíz y subcarpetas con paginación;
- buscar en toda la unidad;
- consultar cuota;
- crear carpetas;
- subir archivos de hasta 250 GB, sujeto a la cuota disponible;
- usar sesiones fragmentadas para archivos mayores de 10 MiB;
- mostrar progreso, permitir cancelación y reintentar bloques interrumpidos;
- descargar mediante streaming;
- renombrar y mover;
- enviar elementos a la papelera;
- consultar metadatos.

## Comportamiento seguro

- Una subida falla si ya existe un elemento con el mismo nombre; no reemplaza en silencio.
- Las cargas grandes se dividen en bloques de 10 MiB, múltiplo de 320 KiB, y nunca se
  cargan completas en memoria.
- La URL preautorizada de una sesión solo se acepta desde hosts oficiales y nunca recibe el
  token OAuth ni se escribe en los logs.
- Al cancelar, la aplicación descarta en OneDrive la sesión temporal.
- Renombrado y eliminación usan el ETag conocido. Un cambio externo produce un conflicto en
  lugar de sobrescribir una versión más reciente.
- La descarga se escribe primero en un archivo `.part` temporal. El destino definitivo solo
  se reemplaza después de terminar correctamente.
- Los enlaces `@odata.nextLink` solo se siguen cuando usan HTTPS y el host oficial de Graph.
- `DELETE` de DriveItem envía el elemento a la papelera; no realiza borrado permanente.

## Errores y reintentos

| Estado | Comportamiento |
|---|---|
| Sin red/timeout | Reintento limitado y mensaje recuperable. |
| 401 | Solicita renovar la sesión. |
| 403 | Informa falta de permisos. |
| 404 | Informa que el elemento fue eliminado externamente. |
| 409/412 | Detecta nombre duplicado o ETag desactualizado. |
| 429 | Respeta `Retry-After`. |
| 5xx | Backoff limitado y error de servicio. |

## Fuera de alcance

- Persistencia de transferencias y recuperación después de reiniciar la aplicación: Módulo 6.
- Cola de varias transferencias simultáneas: Módulo 6.
- Delta Query y refresco periódico: Módulo 7.
- Papelera propia y restauración automatizada: fase posterior.
- Proyectos, equipos y permisos por carpeta: Módulos 4 y 5.
