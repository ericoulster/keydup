"""Main window: toolbar (add folder, rescan, search), track table,
status bar with scan progress."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableView,
    QToolBar,
)

from keydup.library import LibraryService
from keydup.ui.track_table import COL_STATUS, TrackFilterProxy, TrackTableModel


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
        self.setCentralWidget(self.table)

        self._build_toolbar()
        self._build_statusbar()
        self._connect_library()
        self._restore_geometry()

        self.model.set_tracks(self.library.all_tracks())

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
        self.cancel_button.clicked.connect(self.library.cancel_scans)
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

    # -- behavior ----------------------------------------------------------

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
        self.library.cancel_scans()
        super().closeEvent(event)
