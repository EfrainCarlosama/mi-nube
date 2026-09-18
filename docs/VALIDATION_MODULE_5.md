# Validación del Módulo 5

**Fecha:** 17/09/2026  
**Modalidad:** OneDrive Personal

## Automatización

Las pruebas verifican:

- migración SQLite para integrantes, reglas e historial;
- traducción de roles a `read` y `write`;
- normalización y unicidad de correo por proyecto;
- invitación Graph y análisis del permiso devuelto;
- reglas diferentes para Arquitectura y Estructuras;
- conservación del nivel interno aunque Graph use un permiso más amplio;
- revocación de todos los permisos directos al retirar un integrante;
- lectura y eliminación de permisos mediante transporte HTTP simulado;
- construcción y navegación de la interfaz actualizada.

## Validación real

Se restauró la cuenta personal mediante DPAPI y se consultaron los permisos reales de
`Mi Nube - Trabajo`. Graph devolvió un permiso propietario (`owner`) y ninguna herencia, sin
exponer tokens ni datos de identidad en la salida.

La invitación y revocación real de un tercero quedan pendientes porque requieren un correo
Microsoft de prueba elegido por el propietario. La aplicación no enviará invitaciones de
prueba a direcciones no autorizadas.
