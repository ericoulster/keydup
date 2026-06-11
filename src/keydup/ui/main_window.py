"""Main window: toolbar (add folder, rescan, search), track table,
status bar with scan progress."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction
import os

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from keydup.domain import Track
from keydup.library import LibraryService
from keydup.ui.filter_bar import FilterBar
from keydup.ui.player_bar import PlayerBar
from keydup.ui.reveal import reveal_in_file_manager
from keydup.ui.tag_panel import TagPanel
from keydup.ui.track_table import (
    COL_POS,
    COL_STATUS,
    TrackFilterProxy,
    TrackTableModel,
)


class MainWindow(QMainWindow):
    def __init__(self, library: LibraryService):
        super().__init__()
        self.library = library
        self.setWindowTitle("key'd up")

        self.model = TrackTableModel(self)
        self.proxy = TrackFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self.table = QTableView(self)
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(COL_STATUS, 28)
        self.table.doubleClicked.connect(self._play_index)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)

        self.player = PlayerBar(self)
        self.player.error.connect(
            lambda msg: self.statusBar().showMessage(f"Playback: {msg}", 5000)
        )
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.table, 1)
        central_layout.addWidget(self.player)
        self.setCentralWidget(central)

        space = QShortcut(QKeySequence(Qt.Key_Space), self.table)
        space.setContext(Qt.WidgetShortcut)
        space.activated.connect(self.player.toggle)

        self.filter_bar = FilterBar(self.proxy, self)
        dock = QDockWidget("Filters", self)
        dock.setObjectName("filters_dock")
        dock.setWidget(self.filter_bar)
        dock.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable
        )
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

        self.tag_panel = TagPanel(library, self)
        self.tag_panel.filter_changed.connect(self.proxy.set_tag_ids)
        self.tag_panel.active_set_changed.connect(self._on_active_set)
        tag_dock = QDockWidget("Tags", self)
        tag_dock.setObjectName("tags_dock")
        tag_dock.setWidget(self.tag_panel)
        tag_dock.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable
        )
        self.addDockWidget(Qt.LeftDockWidgetArea, tag_dock)

        self._build_toolbar()
        self._build_statusbar()
        self._connect_library()
        self._restore_geometry()

        self.model.set_tracks(self.library.all_tracks())
        self._update_count()
        if self.library.auto_analyze:
            # resume any analysis left over from a previous session
            QTimer.singleShot(500, self.library.start_analysis)

    # -- chrome ------------------------------------------------------------

    def _build_toolbar(self) -> None:
        bar = QToolBar("Main", self)
        bar.setMovable(False)
        self.addToolBar(bar)

        add = QAction("Add Folder…", self)
        add.triggered.connect(self._pick_folder)
        bar.addAction(add)

        rescan = QAction("Rescan", self)
        rescan.triggered.connect(self.library.rescan_all)
        bar.addAction(rescan)

        bar.addSeparator()

        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search artist, title, filename…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(360)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(
            lambda: self.proxy.set_text(self.search.text())
        )
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        bar.addWidget(self.search)

    def _build_statusbar(self) -> None:
        self.status_label = QLabel("", self)
        self.statusBar().addWidget(self.status_label, 1)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self._cancel_work)
        self.statusBar().addPermanentWidget(self.cancel_button)
        self._update_count()

    def _connect_library(self) -> None:
        lib = self.library
        lib.tracks_upserted.connect(self._on_tracks_changed)
        lib.tracks_removed_from_disk.connect(self._on_tracks_changed)
        lib.scan_started.connect(
            lambda path: self._set_busy(f"Scanning {path}…")
        )
        lib.scan_progress.connect(
            lambda done, total: self.status_label.setText(f"Scanning… {done}/{total}")
        )
        lib.scan_finished.connect(self._on_scan_finished)
        lib.scan_failed.connect(
            lambda msg: self._set_idle(f"Scan failed: {msg}")
        )
        lib.analysis_started.connect(
            lambda n: self._set_busy(f"Analyzing {n} tracks…")
        )
        lib.analysis_progress.connect(
            lambda done, total: self._set_busy(f"Analyzing… {done}/{total}")
        )
        lib.analysis_finished.connect(
            lambda: self._set_idle(f"{self.model.rowCount()} tracks - analysis complete")
        )
        lib.analysis_failed.connect(
            lambda msg: self._set_idle(f"Analysis unavailable: {msg}")
        )
        lib.export_progress.connect(
            lambda done, total: self.status_label.setText(f"Exporting… {done}/{total}")
        )
        lib.export_finished.connect(self._set_idle)
        lib.export_failed.connect(lambda msg: self._set_idle(f"Export failed: {msg}"))

    # -- behavior ----------------------------------------------------------

    def _on_active_set(self, tag_id) -> None:
        self.model.set_active_set(tag_id)
        if tag_id is not None:
            self.table.sortByColumn(COL_POS, Qt.AscendingOrder)

    def _track_for_proxy_row(self, proxy_index) -> Track:
        source = self.proxy.mapToSource(proxy_index)
        return self.model.track_at(source.row())

    def _play_index(self, proxy_index) -> None:
        track = self._track_for_proxy_row(proxy_index)
        if not os.path.exists(track.path):
            self.statusBar().showMessage(f"File missing: {track.path}", 5000)
            return
        self.player.play_track(track)

    def _table_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        track = self._track_for_proxy_row(index)
        selected = [
            self._track_for_proxy_row(i)
            for i in self.table.selectionModel().selectedRows()
        ] or [track]

        menu = QMenu(self)
        play = menu.addAction("Play")
        reveal = menu.addAction("Reveal in file manager")
        move_up = move_down = None
        active_set = self.model.active_set_id
        if active_set is not None and active_set in track.tag_ids:
            menu.addSeparator()
            move_up = menu.addAction("Move up in set")
            move_down = menu.addAction("Move down in set")
        menu.addSeparator()
        tags_menu = menu.addMenu("Tags")
        tag_actions = {}
        for tag in self.library.list_tags():
            action = tags_menu.addAction(f"{tag.name} ({tag.kind})")
            action.setCheckable(True)
            action.setChecked(all(tag.id in t.tag_ids for t in selected))
            tag_actions[action] = tag
        tags_menu.addSeparator()
        new_genre = tags_menu.addAction("New genre…")
        new_set = tags_menu.addAction("New set…")
        menu.addSeparator()
        reanalyze = menu.addAction(
            f"Re-analyze ({len(selected)})" if len(selected) > 1 else "Re-analyze"
        )

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == play:
            self._play_index(index)
        elif chosen == reveal:
            reveal_in_file_manager(track.path)
        elif move_up is not None and chosen == move_up:
            self.library.move_in_set(active_set, track.id, -1)
        elif move_down is not None and chosen == move_down:
            self.library.move_in_set(active_set, track.id, +1)
        elif chosen == reanalyze:
            self.library.reanalyze([t.id for t in selected])
        elif chosen in (new_genre, new_set):
            kind = "genre" if chosen == new_genre else "set"
            name, ok = QInputDialog.getText(self, f"New {kind}", "Name:")
            if ok and name.strip():
                tag = self.library.create_tag(name.strip(), kind)
                for t in selected:
                    self.library.set_track_tag(t.id, tag.id, True)
        elif chosen in tag_actions:
            tag = tag_actions[chosen]
            for t in selected:
                self.library.set_track_tag(t.id, tag.id, chosen.isChecked())

    def _cancel_work(self) -> None:
        self.library.cancel_scans()
        self.library.cancel_analysis()
        self._set_idle("Cancelled")

    def _pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add music folder")
        if path:
            self.library.add_folder(path)

    def _on_tracks_changed(self, tracks: list) -> None:
        self.model.upsert_tracks(tracks)
        self._update_count()

    def _on_scan_finished(self, message: str) -> None:
        self._set_idle(message)
        self._update_count()

    def _set_busy(self, message: str) -> None:
        self.status_label.setText(message)
        self.cancel_button.show()

    def _set_idle(self, message: str) -> None:
        self.status_label.setText(message)
        self.cancel_button.hide()

    def _update_count(self) -> None:
        n = self.model.rowCount()
        if not self.cancel_button.isVisible():
            self.status_label.setText(f"{n} tracks")

    # -- geometry persistence ------------------------------------------------

    def _restore_geometry(self) -> None:
        settings = QSettings("keydup", "keydup")
        geometry = settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1100, 700)

    def closeEvent(self, event) -> None:
        QSettings("keydup", "keydup").setValue("geometry", self.saveGeometry())
        self.library.shutdown()
        super().closeEvent(event)
