from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QPlainTextEdit

from common import norm_item_id


class BazaarCraftTrackerTab(QWidget):
    """
    Version "from scratch" minimaliste:
    - Une liste d'items à surveiller
    - Un bouton pour les envoyer rapidement vers le filtre Crafts
    """
    def __init__(self, main):
        super().__init__()
        self.main = main

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.btn_send_to_crafts = QPushButton("Send first item to Crafts filter")
        self.lbl = QLabel("Items list (one per line)")
        top.addWidget(self.btn_send_to_crafts)
        top.addWidget(self.lbl, 1)
        root.addLayout(top)

        self.txt = QPlainTextEdit()
        self.txt.setPlaceholderText("Example:\nENCHANTED_SUGAR\nENCHANTED_COBBLESTONE\n...")
        root.addWidget(self.txt, 1)

        self.btn_send_to_crafts.clicked.connect(self._send)

    def _send(self) -> None:
        lines = [norm_item_id(x) for x in self.txt.toPlainText().splitlines() if norm_item_id(x)]
        if not lines:
            return
        # on pousse dans le filter de l’onglet crafts si dispo
        if getattr(self.main, "tab_crafts", None) is not None:
            self.main.tab_crafts.ed_filter.setText(lines[0])
            self.main.tabs.setCurrentWidget(self.main.tab_crafts)
