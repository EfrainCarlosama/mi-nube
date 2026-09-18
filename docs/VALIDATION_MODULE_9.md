# Validación del Módulo 9

Fecha: 18/09/2026  
Versión: 0.9.0

## Resultado

- Dos compilaciones limpias consecutivas produjeron el mismo SHA-256 para `MiNube.exe`:
  `fb50739ba43f1c616ebf7bfd8ba9c6846749cb27fa3905cc88fcfaedb07c1b14`.
- El ejecutable empaquetado superó `--smoke-test` sin depender de Python instalado.
- `MiNubeSetup.exe` se instaló silenciosamente para el usuario actual con código 0.
- La copia instalada superó `--smoke-test` con código 0.
- El desinstalador terminó con código 0 y eliminó los binarios instalados.
- El manifiesto de muestra fue firmado y verificado con Ed25519.
- Las pruebas rechazan firma alterada, URL no HTTPS, tamaño/hash incorrectos y descargas
  incompletas.
- Las pruebas de migración fuerzan un fallo y confirman la restauración del contenido SQLite.

## Comportamiento de datos al desinstalar

Por omisión, la desinstalación conserva `%LOCALAPPDATA%\MiNube`: base SQLite, caché DPAPI,
logs y portadas. Esto permite reinstalar sin perder el historial. El asistente ofrece borrar
esa carpeta al final; una instalación silenciosa mantiene los datos deliberadamente.

## Pendiente externo

Los artefactos validados no tienen firma Authenticode porque el equipo no dispone todavía de
un certificado público de firma de código ni de SignTool. Windows puede mostrar “Editor
desconocido”. Antes de publicar a terceros se debe instalar el certificado, ejecutar el build
con `-RequireSignature` y comprobar estado `Valid`.
