"""Tag panel dock: genre and set tags, checkable for filtering.

Checked tags filter the table (any-match). Tag assignment to tracks
happens from the table's context menu."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
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
KIND_ROLE = Qt.UserRole + 1


class TagPanel(QWidget):
    filter_changed = Signal(object)        # frozenset[int]
    active_set_changed = Signal(object)    # tag id (int) | None
    session_filter_changed = Signal(bool)  # "only new this session"

    def __init__(self, library: LibraryService, parent=None):
        super().__init__(parent)
        self.library = library
        self._session_count = 0

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemChanged.connect(self._emit_filter)
        self._session_item: QTreeWidgetItem | None = None

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
        session_on = self.session_active()
        self.tree.blockSignals(True)
        self.tree.clear()

        # pinned, system-managed: tracks added during this run
        self._session_item = QTreeWidgetItem([self._session_label()])
        self._session_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        self._session_item.setCheckState(
            0, Qt.Checked if session_on else Qt.Unchecked
        )
        self.tree.addTopLevelItem(self._session_item)

        roots: dict[str, QTreeWidgetItem] = {}
        for kind, label in KIND_LABELS.items():
            root = QTreeWidgetItem([label])
            root.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(root)
            roots[kind] = root
        for tag in self.library.list_tags():
            item = QTreeWidgetItem([tag.name])
            item.setData(0, Qt.UserRole, tag.id)
            item.setData(0, KIND_ROLE, tag.kind)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(
                0, Qt.Checked if tag.id in checked else Qt.Unchecked
            )
            roots[tag.kind].addChild(item)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        self._emit_filter()

    def _checked_items(self) -> list[QTreeWidgetItem]:
        items = []
        for r in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(r)
            for c in range(root.childCount()):
                child = root.child(c)
                if child.checkState(0) == Qt.Checked:
                    items.append(child)
        return items

    def checked_tag_ids(self) -> frozenset[int]:
        return frozenset(i.data(0, Qt.UserRole) for i in self._checked_items())

    def active_set_id(self) -> int | None:
        """The single checked tag, when it is a set - drives the ordered
        # column and move up/down actions."""
        checked = self._checked_items()
        if len(checked) == 1 and checked[0].data(0, KIND_ROLE) == "set":
            return checked[0].data(0, Qt.UserRole)
        return None

    def session_active(self) -> bool:
        item = self._session_item
        return item is not None and item.checkState(0) == Qt.Checked

    def _session_label(self) -> str:
        return f"✦ New this session ({self._session_count})"

    def set_session_count(self, count: int) -> None:
        self._session_count = count
        if self._session_item is not None:
            self.tree.blockSignals(True)
            self._session_item.setText(0, self._session_label())
            self.tree.blockSignals(False)

    def _emit_filter(self, *_args) -> None:
        self.filter_changed.emit(self.checked_tag_ids())
        self.active_set_changed.emit(self.active_set_id())
        self.session_filter_changed.emit(self.session_active())

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
        tag_id = item.data(0, Qt.UserRole)
        menu = QMenu(self)
        export = None
        if item.data(0, KIND_ROLE) == "set":
            export = menu.addAction(f"Export set '{item.text(0)}' to folder…")
        delete = menu.addAction(f"Delete tag '{item.text(0)}'")
        chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == delete:
            self.library.delete_tag(tag_id)
        elif chosen == export:
            dest = QFileDialog.getExistingDirectory(
                self, f"Export '{item.text(0)}' into folder"
            )
            if dest:
                self.library.export_set(tag_id, dest)
