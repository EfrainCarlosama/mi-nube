# Empaquetado y publicación de Mi Nube

## 1. Requisitos del equipo de compilación

- Windows 10 u 11 de 64 bits.
- Entorno `.venv` con `pip install -e ".[dev]"`.
- Inno Setup 7 para producir `MiNubeSetup.exe`.
- Windows SDK SignTool y un certificado Authenticode para una publicación pública.

El Client ID de Microsoft Entra es un identificador público, no una contraseña. El build lo
toma del `.env` junto con el tenant y la URL del canal, y los incorpora a la configuración
de ejecución. Nunca se incorpora un client secret.

## 2. Compilación local

```powershell
.\scripts\build_windows.ps1
```

El resultado se guarda en `dist`:

- `MiNube/MiNube.exe`: aplicación autocontenida.
- `MiNubeSetup.exe`: instalador por usuario.
- `checksums.sha256`: hashes de los dos ejecutables.
- `build-info.json`: versión de Python, PyInstaller y datos del build.

El script borra únicamente `build` y `dist` dentro del proyecto, fija
`PYTHONHASHSEED`/`SOURCE_DATE_EPOCH`, limita el `PATH`, ejecuta PyInstaller, prueba el
ejecutable y finalmente invoca Inno Setup.

## 3. Firma Authenticode

Instale el certificado en el almacén del usuario, copie su huella SHA-1 sin espacios y
compile así:

```powershell
$env:MI_NUBE_SIGN_CERT_SHA1 = "HUELLA_DEL_CERTIFICADO"
$env:MI_NUBE_TIMESTAMP_URL = "https://URL_RFC3161_DEL_PROVEEDOR"
.\scripts\build_windows.ps1 -RequireSignature
```

La aplicación y el instalador se firman con SHA-256 y se verifican antes de finalizar. Si se
usa `-RequireSignature`, la compilación falla cuando el certificado o SignTool no están
disponibles. No publique una versión marcada como `NotSigned`.

## 4. Canal de actualización

La clave privada de actualizaciones se crea una sola vez:

```powershell
python .\scripts\generate_update_key.py
```

Se guarda protegida con Windows DPAPI en
`%LOCALAPPDATA%\MiNube\release-keys\update-private.dpapi`. El archivo público se incluye en
la aplicación. Respaldar la clave privada requiere un procedimiento seguro asociado al mismo
usuario/equipo o la rotación explícita de la clave pública en una nueva versión.

Después de subir el instalador a su URL HTTPS definitiva:

```powershell
$env:MI_NUBE_INSTALLER_URL = "https://updates.ejemplo.com/MiNubeSetup.exe"
.\scripts\build_windows.ps1 -RequireSignature
```

El build crea `dist/update-manifest.json`. Publique ese archivo también por HTTPS y configure
su dirección en `MI_NUBE_UPDATE_URL` durante el build de la aplicación. No use la URL
`example.invalid` del manifiesto de muestra; solo existe para la validación local.

## 5. Prueba previa a publicación

1. Verificar que `Get-AuthenticodeSignature` indique `Valid` en ambos ejecutables.
2. Instalar en una cuenta estándar de Windows y abrir Mi Nube.
3. Confirmar restauración de sesión, lectura de OneDrive y una transferencia de prueba.
4. Publicar primero el instalador y después el manifiesto firmado.
5. Probar la actualización desde la versión anterior.
6. Desinstalar y comprobar tanto conservar como eliminar los datos locales.

La evidencia técnica del Módulo 9 está en [VALIDATION_MODULE_9.md](VALIDATION_MODULE_9.md).
