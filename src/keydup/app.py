"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from keydup import paths
from keydup.db import Database
from keydup.library import LibraryService
from keydup.ui.main_window import MainWindow
from keydup.ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("key'd up")
    app.setOrganizationName("keydup")
    app.setDesktopFileName("keydup")
    apply_theme(app)

    db = Database(paths.db_path())
    library = LibraryService(db)
    window = MainWindow(library)
    window.show()

    code = app.exec()
    db.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
