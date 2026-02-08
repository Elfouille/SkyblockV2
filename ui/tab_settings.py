from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QMessageBox,
)

from settings import AppSettings, save_settings


class SettingsTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main

        root = QVBoxLayout(self)

        title = QLabel("Paramètres de l'application")
        title.setStyleSheet("font-weight: 700; font-size: 16px;")
        root.addWidget(title)

        form = QFormLayout()

        self.ed_api_key = QLineEdit()
        self.ed_api_key.setPlaceholderText("Votre clé Hypixel (cache/hypixel_key.json)")
        self.ed_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Clé API Hypixel:", self.ed_api_key)

        self.sp_bazaar_cache = QSpinBox()
        self.sp_bazaar_cache.setRange(10, 3600)
        self.sp_bazaar_cache.setSuffix(" sec")
        form.addRow("Cache bazaar:", self.sp_bazaar_cache)

        self.sp_items_cache = QSpinBox()
        self.sp_items_cache.setRange(1, 60)
        self.sp_items_cache.setSuffix(" jours")
        form.addRow("Cache items:", self.sp_items_cache)

        self.ck_enable_icons = QCheckBox("Afficher les icônes (si dispo)")
        form.addRow("", self.ck_enable_icons)

        self.ck_allow_downloads = QCheckBox("Autoriser le téléchargement des icônes")
        form.addRow("", self.ck_allow_downloads)

        self.ck_auto_items = QCheckBox("Auto-refresh: Bazaar Items")
        form.addRow("", self.ck_auto_items)

        self.ck_auto_crafts = QCheckBox("Auto-refresh: Crafts")
        form.addRow("", self.ck_auto_crafts)

        # ✅ NEW: Museum auto-refresh
        self.ck_auto_museum = QCheckBox("Auto-refresh: Museum")
        form.addRow("", self.ck_auto_museum)

        self.sp_museum_refresh = QSpinBox()
        self.sp_museum_refresh.setRange(10, 3600)
        self.sp_museum_refresh.setSuffix(" sec")
        form.addRow("Museum refresh interval:", self.sp_museum_refresh)

        self.sp_museum_ttl = QSpinBox()
        self.sp_museum_ttl.setRange(10, 3600)
        self.sp_museum_ttl.setSuffix(" sec")
        form.addRow("Museum cache TTL:", self.sp_museum_ttl)

        root.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.btn_apply = QPushButton("Appliquer")
        actions.addWidget(self.btn_apply)
        root.addLayout(actions)

        root.addStretch(1)

        self.btn_apply.clicked.connect(self._apply)

        self.load_from_settings(self.main.settings)

    def load_from_settings(self, settings: AppSettings) -> None:
        self.ed_api_key.setText(settings.api_key)
        self.sp_bazaar_cache.setValue(int(settings.bazaar_cache_seconds))
        self.sp_items_cache.setValue(int(settings.items_cache_days))
        self.ck_enable_icons.setChecked(bool(settings.enable_icons))
        self.ck_allow_downloads.setChecked(bool(settings.allow_icon_downloads))
        self.ck_auto_items.setChecked(bool(settings.auto_refresh_items))
        self.ck_auto_crafts.setChecked(bool(settings.auto_refresh_crafts))

        # ✅ NEW
        self.ck_auto_museum.setChecked(bool(settings.auto_refresh_museum))
        self.sp_museum_refresh.setValue(int(settings.museum_refresh_seconds))
        self.sp_museum_ttl.setValue(int(settings.museum_cache_ttl_seconds))

    def _apply(self) -> None:
        new_settings = AppSettings(
            api_key=self.ed_api_key.text().strip(),
            bazaar_cache_seconds=int(self.sp_bazaar_cache.value()),
            items_cache_days=int(self.sp_items_cache.value()),
            enable_icons=self.ck_enable_icons.isChecked(),
            allow_icon_downloads=self.ck_allow_downloads.isChecked(),
            auto_refresh_items=self.ck_auto_items.isChecked(),
            auto_refresh_crafts=self.ck_auto_crafts.isChecked(),

            # ✅ NEW
            auto_refresh_museum=self.ck_auto_museum.isChecked(),
            museum_refresh_seconds=int(self.sp_museum_refresh.value()),
            museum_cache_ttl_seconds=int(self.sp_museum_ttl.value()),
        )
        save_settings(new_settings)
        self.main.apply_settings(new_settings)
        QMessageBox.information(self, "Paramètres", "Paramètres appliqués.")
