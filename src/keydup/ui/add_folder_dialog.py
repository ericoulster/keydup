"""Dialog shown after picking a folder to add: optionally tag every
track in it as a genre or a set (named after the folder by default)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)


class AddFolderDialog(QDialog):
    def __init__(self, folder_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add folder")
        folder_name = Path(folder_path).name

        self.none_radio = QRadioButton("Just add the tracks", self)
        self.genre_radio = QRadioButton("Also tag all tracks as a genre", self)
        self.set_radio = QRadioButton("Also tag all tracks as a set", self)
        self.none_radio.setChecked(True)

        self.name_edit = QLineEdit(folder_name, self)
        self.name_edit.setEnabled(False)

        group = QButtonGroup(self)
        for radio in (self.none_radio, self.genre_radio, self.set_radio):
            group.addButton(radio)
        self.genre_radio.toggled.connect(self._sync_name)
        self.set_radio.toggled.connect(self._sync_name)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Add <b>{folder_name}</b> to the library.", self))
        layout.addWidget(self.none_radio)
        layout.addWidget(self.genre_radio)
        layout.addWidget(self.set_radio)
        layout.addWidget(QLabel("Tag name:", self))
        layout.addWidget(self.name_edit)
        layout.addWidget(buttons)

    def _sync_name(self, *_args) -> None:
        self.name_edit.setEnabled(
            self.genre_radio.isChecked() or self.set_radio.isChecked()
        )

    def auto_tag(self) -> tuple[str, str] | None:
        """(kind, name) to apply to the folder's tracks, or None."""
        name = self.name_edit.text().strip()
        if not name:
            return None
        if self.genre_radio.isChecked():
            return ("genre", name)
        if self.set_radio.isChecked():
            return ("set", name)
        return None
