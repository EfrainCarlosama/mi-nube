# Configuración de autenticación Microsoft

Mi Nube usa MSAL como **cliente público de escritorio**. La aplicación no requiere ni debe
distribuir un `client secret`. El inicio interactivo se abre en el navegador del sistema y
MSAL aplica PKCE automáticamente.

## 1. Registrar la aplicación

1. Ingrese al centro de administración de Microsoft Entra.
2. Abra **Identidad → Aplicaciones → Registros de aplicaciones → Nuevo registro**.
3. Use el nombre `Mi Nube Desktop`.
4. Elija el tipo de cuenta apropiado:
   - **Solo este directorio** para una aplicación interna de una organización.
   - **Cualquier directorio y cuentas personales** solo si realmente se admitirán ambos.
5. Finalice el registro y copie:
   - **Id. de aplicación (cliente)**.
   - **Id. de directorio (inquilino)** para una aplicación de un solo tenant.

## 2. Configurar la plataforma

1. En el registro, abra **Autenticación → Agregar una plataforma**.
2. Seleccione **Aplicaciones móviles y de escritorio**.
3. Agregue `http://localhost` como URI de redirección para el navegador del sistema.
4. Compruebe que el flujo de cliente público esté permitido cuando la configuración del
   tenant lo requiera.

No cree un secreto de cliente: un ejecutable de escritorio no puede conservarlo de forma
confidencial.

## 3. Permisos delegados

En **Permisos de API → Microsoft Graph**, agregue inicialmente:

- `User.Read`: iniciar sesión y leer el perfil del usuario.
- `Files.ReadWrite`: leer y administrar los archivos a los que accede el usuario conectado.

Mi Nube solicita permisos delegados: actúa en nombre del usuario que inició sesión. No usa
permisos de aplicación ni acceso sin usuario.

## 4. Configuración local

Copie `.env.example` a `.env` y complete los identificadores:

```dotenv
MICROSOFT_CLIENT_ID=00000000-0000-0000-0000-000000000000
MICROSOFT_TENANT_ID=00000000-0000-0000-0000-000000000000
```

Para una aplicación multi-tenant puede mantener `MICROSOFT_TENANT_ID=common`. El archivo
`.env` está excluido del control de versiones.

## 5. Protección de la sesión

MSAL guarda access/refresh tokens en su caché serializada. Mi Nube cifra esa caché con
Windows DPAPI para el usuario actual y la almacena en:

```text
%LOCALAPPDATA%\MiNube\auth\msal-cache.bin
```

Copiar el archivo a otra cuenta de Windows no permite descifrarlo. Al cerrar sesión desde la
aplicación se eliminan las cuentas de la caché y el archivo local. Esto borra la sesión local;
la revocación global de sesiones se administra desde la cuenta Microsoft/Entra.

## Referencias oficiales

- https://learn.microsoft.com/entra/identity-platform/scenario-desktop-app-configuration
- https://learn.microsoft.com/entra/msal/python/getting-started/acquiring-tokens
- https://learn.microsoft.com/entra/msal/python/advanced/msal-python-token-cache-serialization
- https://learn.microsoft.com/graph/permissions-reference
