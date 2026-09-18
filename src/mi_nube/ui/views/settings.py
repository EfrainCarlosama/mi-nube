from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mi_nube import __version__
from mi_nube.app.settings import Settings
from mi_nube.domain.identity import public_display_name
from mi_nube.domain.models import AccountProfile
from mi_nube.ui.views.common import page_header
from mi_nube.updates.models import UpdateCheckResult


class SettingsView(QWidget):
    sign_in_requested = Signal()
    sign_out_requested = Signal()
    check_updates_requested = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._profile: AccountProfile | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(18)
        title, subtitle = page_header(
            "Configuración",
            "Cuenta Microsoft y preferencias de Mi Nube",
        )
        layout.addWidget(title)
        layout.addWidget(subtitle)

        account_card = QFrame()
        account_card.setProperty("card", True)
        account_layout = QVBoxLayout(account_card)
        account_layout.setContentsMargins(22, 20, 22, 20)
        account_layout.setSpacing(16)

        heading = QLabel("Cuenta Microsoft 365")
        heading.setObjectName("SectionTitle")
        account_layout.addWidget(heading)

        profile_row = QHBoxLayout()
        self._avatar = QLabel("—")
        self._avatar.setObjectName("AccountAvatar")
        self._avatar.setFixedSize(48, 48)
        self._avatar.setAlignment(self._avatar.alignment().AlignCenter)
        identity = QVBoxLayout()
        self._account_name = QLabel("No has iniciado sesión")
        self._account_name.setStyleSheet("font-size: 15px; font-weight: 650;")
        self._account_email = QLabel(
            "Mi Nube abrirá el navegador oficial de Microsoft para autenticarte."
        )
        self._account_email.setObjectName("Muted")
        self._account_email.setWordWrap(True)
        identity.addWidget(self._account_name)
        identity.addWidget(self._account_email)
        profile_row.addWidget(self._avatar)
        profile_row.addSpacing(10)
        profile_row.addLayout(identity, 1)
        account_layout.addLayout(profile_row)

        self._configuration_status = QLabel()
        self._configuration_status.setWordWrap(True)
        account_layout.addWidget(self._configuration_status)

        buttons = QHBoxLayout()
        self._sign_in_button = QPushButton("Iniciar sesión con Microsoft")
        self._sign_in_button.setProperty("primary", True)
        self._sign_in_button.clicked.connect(self.sign_in_requested.emit)
        self._sign_out_button = QPushButton("Cerrar sesión en este equipo")
        self._sign_out_button.setProperty("danger", True)
        self._sign_out_button.clicked.connect(self.sign_out_requested.emit)
        buttons.addWidget(self._sign_in_button)
        buttons.addWidget(self._sign_out_button)
        buttons.addStretch()
        account_layout.addLayout(buttons)
        layout.addWidget(account_card)

        security_card = QFrame()
        security_card.setProperty("card", True)
        security_layout = QVBoxLayout(security_card)
        security_layout.setContentsMargins(22, 20, 22, 20)
        security_layout.setSpacing(8)
        security_title = QLabel("Seguridad")
        security_title.setObjectName("SectionTitle")
        security_text = QLabel(
            "Mi Nube nunca recibe ni guarda tu contraseña. El inicio de sesión usa OAuth "
            "con PKCE en el navegador de Microsoft. La caché de sesión se cifra para tu "
            "usuario de Windows mediante DPAPI."
        )
        security_text.setWordWrap(True)
        security_text.setObjectName("PageSubtitle")
        permissions = QLabel(
            "Permisos actuales: leer tu perfil y administrar tus archivos "
            "(User.Read, Files.ReadWrite)."
        )
        permissions.setObjectName("Muted")
        security_layout.addWidget(security_title)
        security_layout.addWidget(security_text)
        security_layout.addWidget(permissions)
        layout.addWidget(security_card)

        update_card = QFrame()
        update_card.setProperty("card", True)
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(22, 20, 22, 20)
        update_layout.setSpacing(9)
        update_title = QLabel("Actualizaciones")
        update_title.setObjectName("SectionTitle")
        self._update_status = QLabel(f"Versión instalada: {__version__}")
        self._update_status.setObjectName("PageSubtitle")
        self._update_status.setWordWrap(True)
        self._update_action_text = "Buscar actualizaciones"
        self._update_button = QPushButton("Buscar actualizaciones")
        self._update_button.setProperty("secondary", True)
        self._update_button.clicked.connect(self.check_updates_requested.emit)
        update_layout.addWidget(update_title)
        update_layout.addWidget(self._update_status)
        update_layout.addWidget(self._update_button)
        layout.addWidget(update_card)
        layout.addStretch()
        self.set_profile(None)
        self.set_update_configured(False)

    def set_profile(self, profile: AccountProfile | None) -> None:
        self._profile = profile
        configured = self._settings.is_microsoft_configured
        if profile:
            display_name = public_display_name(profile.display_name, "Propietario")
            initials = "".join(part[0] for part in display_name.split()[:2]).upper() or "MS"
            self._avatar.setText(initials)
            self._account_name.setText(display_name)
            self._account_email.setText("Cuenta Microsoft autenticada · correo oculto")
            self._configuration_status.setText("● Sesión disponible en este equipo")
            self._configuration_status.setProperty("success", True)
            self._configuration_status.setProperty("warning", False)
        else:
            self._avatar.setText("MS")
            self._account_name.setText("No has iniciado sesión")
            self._account_email.setText(
                "Mi Nube abrirá el navegador oficial de Microsoft para autenticarte."
            )
            if configured:
                self._configuration_status.setText("● Registro de Microsoft configurado")
                self._configuration_status.setProperty("success", True)
                self._configuration_status.setProperty("warning", False)
            else:
                self._configuration_status.setText(
                    "Falta MICROSOFT_CLIENT_ID. Consulta docs/AUTH_SETUP.md "
                    "antes de iniciar sesión."
                )
                self._configuration_status.setProperty("success", False)
                self._configuration_status.setProperty("warning", True)
        self._configuration_status.style().unpolish(self._configuration_status)
        self._configuration_status.style().polish(self._configuration_status)
        self._sign_in_button.setVisible(profile is None)
        self._sign_in_button.setEnabled(configured)
        self._sign_out_button.setVisible(profile is not None)

    def set_busy(self, busy: bool) -> None:
        self._sign_in_button.setEnabled(not busy and self._settings.is_microsoft_configured)
        self._sign_out_button.setEnabled(not busy)
        if busy:
            self._sign_in_button.setText("Esperando a Microsoft...")
        else:
            self._sign_in_button.setText("Iniciar sesión con Microsoft")

    def set_update_configured(self, configured: bool) -> None:
        self._update_button.setEnabled(configured)
        if configured:
            self._update_status.setText(
                f"Versión instalada: {__version__}. Canal seguro configurado."
            )
        else:
            self._update_status.setText(
                f"Versión instalada: {__version__}. El canal de actualización aún no tiene URL."
            )

    def set_update_busy(self, busy: bool) -> None:
        self._update_button.setEnabled(not busy)
        self._update_button.setText("Procesando..." if busy else self._update_action_text)

    def show_update_result(self, result: UpdateCheckResult) -> None:
        if result.available:
            self._update_status.setText(
                f"Nueva versión {result.manifest.version}: {result.manifest.release_notes}"
            )
            self._update_action_text = f"Descargar versión {result.manifest.version}"
        else:
            self._update_status.setText(f"Mi Nube {result.current_version} está actualizado.")
            self._update_action_text = "Buscar actualizaciones"
        self._update_button.setText(self._update_action_text)

    def show_update_progress(self, received: int, total: int) -> None:
        percent = min(100, round(received * 100 / total)) if total else 0
        self._update_status.setText(f"Descargando actualización: {percent} %")

    def show_update_error(self, message: str) -> None:
        self._update_status.setText(message)
        self._update_action_text = "Reintentar"
        self._update_button.setText(self._update_action_text)
