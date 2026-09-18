# Política de privacidad de Mi Nube

Última actualización: 18 de septiembre de 2026.

## Alcance

Mi Nube es una aplicación de escritorio que permite a la persona usuaria trabajar con su
propia cuenta de Microsoft y OneDrive. El proyecto no opera un servicio central que recopile
el contenido de las cuentas conectadas.

## Información procesada

Para ofrecer sus funciones, la aplicación puede procesar:

- la identidad básica devuelta por Microsoft durante el inicio de sesión;
- nombres, identificadores y metadatos de archivos y carpetas de OneDrive;
- correos utilizados expresamente para invitaciones y permisos;
- metadatos de proyectos, transferencias, sincronizaciones y documentos;
- fotografías de portada elegidas por la persona usuaria;
- registros técnicos necesarios para diagnosticar errores.

## Dónde se guarda la información

La base SQLite, la caché de autenticación protegida con Windows DPAPI, los registros y las
portadas se guardan localmente en `%LOCALAPPDATA%\MiNube`. Los archivos administrados por la
aplicación permanecen en la cuenta de OneDrive de la persona usuaria.

El código fuente público no contiene bases locales, archivos de OneDrive, tokens, sesiones,
contraseñas, claves privadas ni la configuración `.env` utilizada en el equipo de desarrollo.

## Comunicaciones externas

Mi Nube se comunica con los servicios de autenticación y Microsoft Graph para ejecutar las
acciones solicitadas por la persona usuaria. También puede consultar por HTTPS el canal de
actualizaciones configurado. Como ocurre con cualquier conexión web, esos proveedores pueden
recibir información técnica normal de la conexión, como la dirección IP.

Mi Nube no incluye publicidad ni telemetría propia y no vende información personal.

## Eliminación y conservación local

La desinstalación conserva por omisión la carpeta local para permitir una reinstalación sin
perder el historial. El asistente de desinstalación ofrece eliminar esos datos. La persona
usuaria también puede borrar `%LOCALAPPDATA%\MiNube` cuando la aplicación esté cerrada.

## Informes de privacidad o seguridad

No publique tokens, capturas con información personal ni documentos privados en incidencias
públicas. Utilice la opción privada **Report a vulnerability** de la pestaña **Security** del
repositorio oficial.
