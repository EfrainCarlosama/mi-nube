# Code signing policy

Free code signing provided by SignPath.io, certificate by SignPath Foundation.

## Proyecto y privacidad

Esta política cubre los ejecutables y el instalador oficial de Mi Nube. El tratamiento de
datos se describe en [PRIVACY.md](PRIVACY.md) y los informes de seguridad en
[SECURITY.md](SECURITY.md).

## Roles

- Committer y reviewer: [`@EfrainCarlosama`](https://github.com/EfrainCarlosama), propietario
  del repositorio oficial.
- Approver de firma: [`@EfrainCarlosama`](https://github.com/EfrainCarlosama), propietario
  del repositorio oficial.
- Las personas colaboradoras futuras deberán figurar expresamente en esta sección antes de
  recibir permisos de escritura, revisión o aprobación.

## Reglas de compilación y firma

- Solo se firman artefactos creados desde el repositorio oficial.
- La compilación se ejecuta en un sistema de compilación confiable vinculado al repositorio.
- El código de publicación procede de la rama protegida `main` y de una etiqueta de versión.
- Cada solicitud de firma de una versión requiere aprobación manual del approver.
- Deben superar la auditoría de privacidad, el análisis de estilo y todas las pruebas.
- Los binarios de dependencias externas no se firman como si fueran código propio.
- No se aceptan ejecutables cargados manualmente desde un equipo particular.

## Artefactos oficiales

- `MiNube.exe`
- `MiNubeSetup.exe`

Una firma confirma el origen y la integridad del artefacto; no sustituye las revisiones de
seguridad. En Windows se puede verificar con:

```powershell
Get-AuthenticodeSignature .\MiNube.exe
Get-AuthenticodeSignature .\MiNubeSetup.exe
```
