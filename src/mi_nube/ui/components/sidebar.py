from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from mi_nube.domain.identity import public_display_name


@dataclass(frozen=True, slots=True)
class NavigationItem:
    key: str
    label: str


NAVIGATION_ITEMS = (
    NavigationItem("home", "Inicio"),
    NavigationItem("personal", "Personal"),
    NavigationItem("work", "Trabajo"),
    NavigationItem("recent", "Recientes"),
    NavigationItem("shared", "Compartidos"),
    NavigationItem("activity", "Actividad"),
    NavigationItem("settings", "Configuración"),
)


class Sidebar(QFrame):
    navigation_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(230)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 24, 18, 20)
        layout.setSpacing(6)

        brand = QHBoxLayout()
        mark = QLabel("MN")
        mark.setObjectName("BrandMark")
        mark.setFixedSize(43, 43)
        mark.setAlignment(mark.alignment() | mark.alignment().AlignCenter)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        name = QLabel("Mi Nube")
        name.setObjectName("BrandName")
        caption = QLabel("Espacio de trabajo")
        caption.setObjectName("BrandCaption")
        brand_text.addWidget(name)
        brand_text.addWidget(caption)
        brand.addWidget(mark)
        brand.addSpacing(9)
        brand.addLayout(brand_text)
        brand.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(28)

        section = QLabel("NAVEGACIÓN")
        section.setObjectName("SidebarCaption")
        layout.addWidget(section)
        layout.addSpacing(4)

        self._buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for item in NAVIGATION_ITEMS:
            button = QPushButton(item.label)
            button.setProperty("nav", True)
            button.setCheckable(True)
            button.setMinimumHeight(43)
            button.clicked.connect(
                lambda checked=False, key=item.key: self.navigation_requested.emit(key)
            )
            group.addButton(button)
            self._buttons[item.key] = button
            layout.addWidget(button)

        layout.addItem(QSpacerItem(1, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #263247;")
        layout.addWidget(divider)
        self._user = QLabel("Sin sesión de Microsoft")
        self._user.setWordWrap(True)
        self._user.setStyleSheet("color: #D8DEEA; font-weight: 600; padding: 10px 2px;")
        layout.addWidget(self._user)
        self.select("home")

    def select(self, key: str) -> None:
        if button := self._buttons.get(key):
            button.setChecked(True)

    def set_user(self, display_name: str | None, _email: str | None = None) -> None:
        if display_name:
            self._user.setText(public_display_name(display_name, "Propietario"))
        else:
            self._user.setText("Sin sesión de Microsoft")
