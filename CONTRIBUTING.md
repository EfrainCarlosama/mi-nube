# Contribuir a Mi Nube

Gracias por ayudar a mejorar Mi Nube.

## Protección de información

Antes de proponer un cambio, ejecute:

```powershell
.\scripts\check_publication_safety.ps1
```

Nunca añada datos reales de una cuenta, archivos `.env`, tokens, bases locales, registros,
claves, certificados privados ni capturas con información personal. Use `example.com` y datos
ficticios en pruebas y documentación.

## Cambios de código

1. Cree una rama para el cambio.
2. Mantenga el cambio limitado y documentado.
3. Ejecute `python -m ruff check src tests`.
4. Ejecute `python -m pytest`.
5. Abra una solicitud de cambios para su revisión.

Las contribuciones se distribuyen bajo `GPL-3.0-only`. Al enviar una contribución, confirma
que tiene derecho a compartirla bajo esa licencia.

## Publicaciones firmadas

Solo el flujo oficial aprobado puede producir publicaciones firmadas. Los ejecutables
creados desde bifurcaciones o equipos particulares no constituyen versiones oficiales de
Mi Nube.
