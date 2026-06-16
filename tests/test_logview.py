"""In-app log capture buffer and viewer."""

from keydup.logcapture import LogBuffer
from keydup.ui.log_window import LogWindow


def test_log_buffer_accumulates_and_caps():
    buf = LogBuffer(max_lines=3)
    received = []
    buf.appended.connect(received.append)
    for line in ("a\n", "b\n", "c\n", "d\n"):
        buf.add(line)
    assert received == ["a\n", "b\n", "c\n", "d\n"]   # every line signalled
    assert buf.snapshot() == "b\nc\nd\n"              # but only last 3 kept


def test_log_window_primes_and_follows(qtbot):
    buf = LogBuffer()
    buf.add("startup line\n")
    window = LogWindow(buf)
    qtbot.addWidget(window)

    assert "startup line" in window.view.toPlainText()
    buf.add("later line\n")
    assert "later line" in window.view.toPlainText()


def test_window_log_toggle(qtbot):
    from keydup.db import Database
    from keydup.library import LibraryService
    from keydup.ui.main_window import MainWindow

    db = Database(":memory:")
    buf = LogBuffer()
    buf.add("hello from the engine\n")
    window = MainWindow(LibraryService(db, auto_analyze=False), log_buffer=buf)
    qtbot.addWidget(window)

    assert window._log_window is None              # hidden by default
    window.show_log_action.setChecked(True)        # View > Show log
    assert window._log_window is not None
    assert window._log_window.isVisible()
    assert "hello from the engine" in window._log_window.view.toPlainText()

    window.show_log_action.setChecked(False)
    assert not window._log_window.isVisible()
    db.close()
