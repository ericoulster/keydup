"""Main window: toolbar (add folder, rescan, search), track table,
status bar with scan progress."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction
import os

from PySide6.QtGui import QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import QMessageBox

import keydup
from keydup import notation
from PySide6.QtWidgets import (
    QDialog,
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
from keydup.ui.add_folder_dialog import AddFolderDialog
from keydup.ui.filter_bar import FilterBar
from keydup.ui.player_bar import PlayerBar
from keydup.ui.reveal import reveal_in_file_manager
from keydup.ui.tag_panel import TagPanel
from keydup.ui.track_table import (
    COL_POS,
    COL_STATUS,
    TrackFilterProxy,
    TrackTableModel,
    TrackTableView,
)


def about_text() -> str:
    return (
        f"<h3>key'd up {keydup.__version__}</h3>"
        "<p>DJ library manager: key &amp; BPM detection, harmonic search, "
        "tags and ordered sets.</p>"
        "<p>Made by <b>Eric Oulster</b><br>"
        '<a href="https://github.com/ericoulster">github.com/ericoulster</a><br>'
        'Source: <a href="https://github.com/ericoulster/keydup">'
        "github.com/ericoulster/keydup</a></p>"
        "<p>Built on <a href='https://github.com/ericoulster/keypipe'>keypipe</a> "
        "(KeyNet + TempoCNN detection).</p>"
        "<p style='font-size: small'>Tempo model: TempoCNN (Schreiber &amp; "
        "M&uuml;ller), weights from the "
        "<a href='https://essentia.upf.edu/models.html'>Essentia models</a> "
        "collection (MTG-UPF), CC BY-NC-SA 4.0.</p>"
    )


class MainWindow(QMainWindow):
    def __init__(self, library: LibraryService, log_buffer=None):
        super().__init__()
        self.library = library
        from keydup.logcapture import LogBuffer

        self._log_buffer = log_buffer if log_buffer is not None else LogBuffer()
        self._log_window = None
        self.setWindowTitle("key'd up")
        self.setAcceptDrops(True)  # drop audio files/folders to import

        self.model = TrackTableModel(self)
        # share the live set so the model's "New" label and the proxy's
        # session filter track exactly what the library marked this run
        self.model.session_new_ids = library.session_new_ids
        self.proxy = TrackFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self.table = TrackTableView(self)
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionsMovable(True)  # drag headers to rearrange columns
        self.table.setColumnWidth(COL_STATUS, 28)
        self.table.setColumnWidth(COL_POS, 36)
        header_state = QSettings("keydup", "keydup").value("header_state")
        if header_state is not None:
            header.restoreState(header_state)
        self.table.rows_dropped.connect(self._on_rows_dropped)
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
        self.tag_panel.session_filter_changed.connect(self.proxy.set_session_new_only)
        tag_dock = QDockWidget("Tags", self)
        tag_dock.setObjectName("tags_dock")
        tag_dock.setWidget(self.tag_panel)
        tag_dock.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable
        )
        self.addDockWidget(Qt.LeftDockWidgetArea, tag_dock)

        self._build_toolbar()
        self._build_menus()
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

    def _build_menus(self) -> None:
        view = self.menuBar().addMenu("&View")
        key_menu = view.addMenu("Key notation")
        group = QActionGroup(self)
        group.setExclusive(True)
        current = notation.saved_notation()
        for name in notation.NOTATIONS:
            action = key_menu.addAction(notation.NOTATION_LABELS[name])
            action.setCheckable(True)
            action.setChecked(name == current)
            action.setData(name)
            group.addAction(action)
        group.triggered.connect(self._on_notation_changed)

        view.addSeparator()
        self.show_log_action = view.addAction("Show log")
        self.show_log_action.setCheckable(True)
        self.show_log_action.toggled.connect(self._toggle_log)

        help_menu = self.menuBar().addMenu("&Help")
        about = help_menu.addAction("About key'd up")
        about.triggered.connect(self._show_about)

    def _show_about(self) -> None:
        QMessageBox.about(self, "About key'd up", about_text())

    def _toggle_log(self, show: bool) -> None:
        if self._log_window is None:
            from keydup.ui.log_window import LogWindow

            self._log_window = LogWindow(self._log_buffer, self)
            self._log_window.closed.connect(
                lambda: self.show_log_action.setChecked(False)
            )
        self._log_window.setVisible(show)
        if show:
            self._log_window.raise_()

    def _on_notation_changed(self, action) -> None:
        name = action.data()
        if name == "custom":
            notation.ensure_custom_template()
            self.statusBar().showMessage(
                f"Custom labels: edit {notation.custom_mapping_path()}", 8000
            )
        notation.save_notation(name)
        formatter = notation.get_formatter(name)
        self.model.set_key_formatter(formatter)
        self.filter_bar.wheel.set_key_formatter(formatter)
        self.player.key_formatter = formatter
        self.player.key_timeline.set_key_formatter(formatter)

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
        lib.waveform_ready.connect(self._on_waveform_ready)
        lib.key_changes_finished.connect(
            lambda: self.statusBar().showMessage("Key-change detection complete", 4000)
        )
        lib.key_changes_failed.connect(
            lambda msg: self.statusBar().showMessage(f"Key detection failed: {msg}", 5000)
        )

    # -- behavior ----------------------------------------------------------

    def _on_active_set(self, tag_id) -> None:
        self.model.set_active_set(tag_id)
        self.table.set_reorder_enabled(tag_id is not None)
        if tag_id is not None:
            self.table.sortByColumn(COL_POS, Qt.AscendingOrder)

    def _on_rows_dropped(self, proxy_rows: list, target_row: int) -> None:
        tag_id = self.model.active_set_id
        if tag_id is None:
            return
        moved = [
            self._track_for_proxy_row(self.proxy.index(r, 0)).id for r in proxy_rows
        ]
        before = None
        if target_row >= 0:
            before = self._track_for_proxy_row(self.proxy.index(target_row, 0)).id
        self.library.reorder_set(tag_id, moved, before)

    def _track_for_proxy_row(self, proxy_index) -> Track:
        source = self.proxy.mapToSource(proxy_index)
        return self.model.track_at(source.row())

    def _playback_block_reason(self, track: Track) -> str | None:
        """Why this track must not be sent to the media backend, or None.

        A file that failed to decode during analysis will not play either,
        and a corrupt/non-audio file has crashed the native backend - so we
        refuse it with the reason rather than risk the crash."""
        from keydup.analysis.probe import looks_like_audio

        if track.status == "error":
            detail = track.error or "the file could not be decoded"
            return f"Can't play {track.filename}: {detail}"
        if not looks_like_audio(track.path):
            return f"Can't play {track.filename}: not an audio file"
        return None

    def _play_index(self, proxy_index) -> None:
        track = self._track_for_proxy_row(proxy_index)
        if not os.path.exists(track.path):
            self.statusBar().showMessage(f"File missing: {track.path}", 5000)
            return
        reason = self._playback_block_reason(track)
        if reason is not None:
            self.statusBar().showMessage(reason, 6000)
            return
        self.player.play_track(track)
        self.player.waveform.set_loading()
        self.library.request_waveform(track)
        segments = self.library.key_segments(track.id)
        if len(segments) > 1:
            self.player.key_timeline.set_segments(segments, track.duration_s)
            self.player.key_timeline.show()
        else:
            self.player.key_timeline.clear()
            self.player.key_timeline.hide()

    def _on_waveform_ready(self, track_id: int, peaks) -> None:
        if self.player.track is not None and self.player.track.id == track_id:
            self.player.waveform.set_peaks(peaks)

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
        detect_keys = menu.addAction(
            f"Detect key changes ({len(selected)})" if len(selected) > 1
            else "Detect key changes"
        )
        reanalyze = menu.addAction(
            f"Re-analyze ({len(selected)})" if len(selected) > 1 else "Re-analyze"
        )

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == play:
            self._play_index(index)
        elif chosen == detect_keys:
            self.library.detect_key_changes([t.id for t in selected])
            self.statusBar().showMessage(
                f"Detecting key changes in {len(selected)} track(s)…", 4000
            )
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
        if not path:
            return
        dialog = AddFolderDialog(path, self)
        if dialog.exec() == QDialog.Accepted:
            self.library.add_folder(path, dialog.auto_tag())

    # -- drag & drop import --------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if paths:
            self.import_paths(paths)
            event.acceptProposedAction()

    def import_paths(self, paths: list) -> None:
        from pathlib import Path

        from keypipe.utils import AUDIO_EXTENSIONS

        dirs = [p for p in paths if Path(p).is_dir()]
        files = [p for p in paths
                 if Path(p).is_file() and Path(p).suffix.lower() in AUDIO_EXTENSIONS]
        # whatever is checked in the tag panel is the filter you are looking
        # at, so a drop files itself under it - including already-known tracks
        tag_ids = self.tag_panel.checked_tag_ids()
        for d in dirs:
            self.library.add_folder(d, tag_ids=tag_ids)
        if files:
            self.library.add_files(files, tag_ids=tag_ids)
        n = len(dirs) + len(files)
        if n:
            message = f"Importing {len(files)} file(s), {len(dirs)} folder(s)…"
            names = [t.name for t in self.library.list_tags() if t.id in tag_ids]
            if names:
                message += f" Tagging: {', '.join(sorted(names))}"
            self.statusBar().showMessage(message, 4000)
        elif paths:
            self.statusBar().showMessage("No audio files in the drop", 4000)

    def _on_tracks_changed(self, tracks: list) -> None:
        self.model.upsert_tracks(tracks)
        self.tag_panel.set_session_count(len(self.library.session_new_ids))
        self._update_count()
        # if the now-playing track just got key-change detection, refresh its strip
        playing = self.player.track
        if playing is not None and any(t.id == playing.id for t in tracks):
            segments = self.library.key_segments(playing.id)
            if len(segments) > 1:
                self.player.key_timeline.set_segments(segments, playing.duration_s)
                self.player.key_timeline.show()
            else:
                self.player.key_timeline.clear()
                self.player.key_timeline.hide()

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
        settings = QSettings("keydup", "keydup")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("header_state", self.table.horizontalHeader().saveState())
        self.library.shutdown()
        super().closeEvent(event)
