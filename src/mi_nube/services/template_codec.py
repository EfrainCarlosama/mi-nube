from __future__ import annotations

from dataclasses import dataclass, field

from mi_nube.domain.models import TemplateFolder
from mi_nube.projects.errors import ProjectValidationError

_INVALID_NAME_CHARS = set('/\\:*?"<>|')


def validate_folder_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ProjectValidationError("Los nombres de carpeta no pueden estar vacíos.")
    if any(character in _INVALID_NAME_CHARS for character in cleaned):
        raise ProjectValidationError(
            f"El nombre “{cleaned}” contiene caracteres no permitidos por OneDrive."
        )
    if cleaned.endswith("."):
        raise ProjectValidationError(f"El nombre “{cleaned}” no puede terminar en punto.")
    return cleaned


@dataclass(slots=True)
class _MutableFolder:
    name: str
    children: list[_MutableFolder] = field(default_factory=list)

    def freeze(self) -> TemplateFolder:
        return TemplateFolder(self.name, tuple(child.freeze() for child in self.children))


def parse_template(text: str) -> tuple[TemplateFolder, ...]:
    roots: list[_MutableFolder] = []
    stack: list[tuple[int, _MutableFolder]] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        if "\t" in raw_line:
            raise ProjectValidationError(
                f"Línea {line_number}: usa espacios en lugar de tabulaciones."
            )
        leading_spaces = len(raw_line) - len(raw_line.lstrip(" "))
        if leading_spaces % 2:
            raise ProjectValidationError(
                f"Línea {line_number}: la sangría debe usar grupos de dos espacios."
            )
        depth = leading_spaces // 2
        name = validate_folder_name(raw_line.strip())
        node = _MutableFolder(name)

        while stack and stack[-1][0] >= depth:
            stack.pop()
        if depth == 0:
            siblings = roots
        else:
            if not stack or stack[-1][0] != depth - 1:
                raise ProjectValidationError(
                    f"Línea {line_number}: falta la carpeta superior para esta sangría."
                )
            siblings = stack[-1][1].children
        if any(sibling.name.casefold() == name.casefold() for sibling in siblings):
            raise ProjectValidationError(
                f"Línea {line_number}: la carpeta “{name}” está repetida en el mismo nivel."
            )
        siblings.append(node)
        stack.append((depth, node))

    if not roots:
        raise ProjectValidationError("La plantilla debe contener al menos una carpeta.")
    return tuple(root.freeze() for root in roots)


def format_template(folders: tuple[TemplateFolder, ...]) -> str:
    lines: list[str] = []

    def append(folder: TemplateFolder, depth: int) -> None:
        lines.append(f"{'  ' * depth}{folder.name}")
        for child in folder.children:
            append(child, depth + 1)

    for root in folders:
        append(root, 0)
    return "\n".join(lines)
