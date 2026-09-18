# Validación del Módulo 6

**Fecha:** 17/09/2026  
**Modalidad:** OneDrive Personal

## Implementación verificada

- migración SQLite v3 y recuperación de trabajos que quedaron `running`;
- cola de varias transferencias con un único trabajo activo;
- pausa, reintento y cancelación desde la interfaz;
- Upload Session reanudable y enlace cifrado con DPAPI;
- consulta del desplazamiento confirmado por OneDrive al reanudar;
- descarga por `Range` contra un enlace temporal renovado;
- conservación del archivo `.part` después de una interrupción;
- verificación final por tamaño y QuickXorHash o SHA-1;
- reemplazo atómico del archivo final;
- rechazo de enlaces preautorizados con host no reconocido.

## Automatización

Las 39 pruebas comprueban, entre otros casos, que una sesión se almacena cifrada, que un
trabajo en curso vuelve a la cola después de reiniciar, que una descarga usa el rango desde
el tamaño ya guardado y que el enlace preautorizado no recibe el encabezado OAuth.

## Validación real

Se creó una carpeta temporal en la raíz de OneDrive y un archivo de 26.214.523 bytes:

1. La subida se pausó después del primer bloque de 10.485.760 bytes.
2. Se reconstruyeron base, repositorio y servicio para simular un reinicio completo.
3. OneDrive confirmó el desplazamiento y la subida terminó con 26.214.523 bytes.
4. La descarga se pausó después de 5.255.168 bytes conservados en `.part`.
5. Se reconstruyó nuevamente el servicio y la descarga continuó mediante `Range`.
6. El archivo final midió 26.214.523 bytes y QuickXorHash coincidió con Graph.

La carpeta remota se envió a la papelera. La carpeta temporal local fue eliminada después de
cerrar el proceso de validación. La base de producción quedó sin trabajos de prueba.
