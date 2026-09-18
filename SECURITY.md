# Política de seguridad

## Versiones compatibles

Mientras Mi Nube permanezca en la serie 0.9, las correcciones de seguridad se aplicarán a la
versión 0.9 más reciente. Las versiones anteriores deberán actualizarse antes de recibir
soporte.

## Cómo informar una vulnerabilidad

Utilice **Security → Report a vulnerability** en el repositorio oficial de GitHub. No abra
una incidencia pública cuando el informe contenga una vulnerabilidad, datos personales,
tokens, credenciales, claves, rutas privadas o capturas de cuentas reales.

Incluya únicamente la información mínima necesaria para reproducir el problema. Sustituya
cuentas, correos, IDs y rutas reales por ejemplos ficticios.

## Tratamiento del informe

El equipo mantenedor confirmará la recepción, evaluará el impacto y coordinará una solución
antes de publicar detalles que puedan facilitar abusos. Una corrección se distribuirá usando
el canal HTTPS y el manifiesto de actualización firmado de Mi Nube.

## Material que nunca debe compartirse

- archivos `.env`;
- cachés de autenticación o tokens;
- bases SQLite y registros locales;
- claves privadas Ed25519 o de firma de código;
- certificados exportados con clave privada;
- documentos o capturas de cuentas reales de OneDrive.
