# Proyectos de trabajo

## Ubicación remota

Los proyectos del Módulo 4 se almacenan en el OneDrive del propietario:

```text
Mi OneDrive/
└── Mi Nube - Trabajo/
    └── Proyecto - Nombre/
        ├── 01 Arquitectura/
        ├── 02 Estructuras/
        └── ...
```

La aplicación local no actúa como servidor y no copia los archivos a SQLite. El ID remoto
de la raíz permite abrir el proyecto aunque una carpeta superior cambie de nombre.

## Plantilla configurable

**Trabajo → Configurar plantilla** presenta el árbol como texto. Cada línea es una carpeta y
cada grupo de dos espacios representa un nivel:

```text
01 Arquitectura
  Planos
  Modelos
02 Estructuras
  Planos
  Cálculos
```

No se admiten nombres vacíos, duplicados entre hermanos, tabulaciones ni caracteres que
OneDrive prohíbe. Guardar incrementa la versión y solo afecta proyectos creados después.

## Persistencia local

La base `%LOCALAPPDATA%\MiNube\mi_nube.db` contiene:

- `schema_migrations`: versiones aplicadas;
- `project_templates`: plantilla predeterminada serializada y versionada;
- `projects`: nombre, cliente, ID de raíz remota y fechas;
- `project_folders`: IDs remotos, jerarquía y ruta relativa de la plantilla.

Las claves foráneas están activas y el alta local completa se confirma en una única
transacción.

## Recuperación ante fallos

La estructura remota se crea antes del registro local. Si Graph o SQLite falla después de
crear la raíz del proyecto, la aplicación envía esa raíz incompleta a la papelera. La carpeta
global `Mi Nube - Trabajo` se conserva porque puede contener otros proyectos.

## Límite del módulo

El Módulo 4 solo organiza proyectos del propietario. Equipo, invitaciones y permisos reales
se definirán en el Módulo 5 después de decidir si OneDrive Personal satisface el modelo de
colaboración o si se necesita SharePoint.
