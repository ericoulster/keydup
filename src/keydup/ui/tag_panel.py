"""Tag panel dock: genre and set tags, checkable for filtering.

Checked tags filter the table (any-match). Tag assignment to tracks
happens from the table's context menu."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from keydup.library import LibraryService

KIND_LABELS = {"genre": "Genres", "set": "Sets"}


class TagPanel(QWidget):
    filter_changed = Signal(object)  # frozenset[int]

    def __init__(self, library: LibraryService, parent=None):
        super().__init__(parent)
        self.library = library

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemChanged.connect(self._emit_filter)

        new_genre = QPushButton("+ Genre", self)
        new_set = QPushButton("+ Set", self)
        new_genre.clicked.connect(lambda: self._new_tag("genre"))
        new_set.clicked.connect(lambda: self._new_tag("set"))

        buttons = QHBoxLayout()
        buttons.addWidget(new_genre)
        buttons.addWidget(new_set)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.tree, 1)
        layout.addLayout(buttons)

        self.library.tags_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        checked = self.checked_tag_ids()
        self.tree.blockSignals(True)
        self.tree.clear()
        roots: dict[str, QTreeWidgetItem] = {}
        for kind, label in KIND_LABELS.items():
            root = QTreeWidgetItem([label])
            root.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(root)
            roots[kind] = root
        for tag in self.library.list_tags():
            item = QTreeWidgetItem([tag.name])
            item.setData(0, Qt.UserRole, tag.id)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(
                0, Qt.Checked if tag.id in checked else Qt.Unchecked
            )
            roots[tag.kind].addChild(item)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        self._emit_filter()

    def checked_tag_ids(self) -> frozenset[int]:
        ids = set()
        for r in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(r)
            for c in range(root.childCount()):
                child = root.child(c)
                if child.checkState(0) == Qt.Checked:
                    ids.add(child.data(0, Qt.UserRole))
        return frozenset(ids)

    def _emit_filter(self, *_args) -> None:
        self.filter_changed.emit(self.checked_tag_ids())

    def _new_tag(self, kind: str) -> None:
        name, ok = QInputDialog.getText(
            self, f"New {kind}", f"{KIND_LABELS[kind][:-1]} name:"
        )
        name = name.strip()
        if ok and name:
            self.library.create_tag(name, kind)

    def _context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None or item.data(0, Qt.UserRole) is None:
            return
        menu = QMenu(self)
        delete = menu.addAction(f"Delete tag '{item.text(0)}'")
        if menu.exec(self.tree.viewport().mapToGlobal(pos)) == delete:
            self.library.delete_tag(item.data(0, Qt.UserRole))
