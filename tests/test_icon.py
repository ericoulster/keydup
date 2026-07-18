"""The app icon ships as a bundled resource and renders through Qt.

Guards two things a broken icon would silently pass otherwise: the SVG is
present in the resources dir the PyInstaller spec collects, and Qt's svg
image plugin can actually rasterize it (a missing qsvg plugin yields a
null icon, not an error)."""

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

from keydup import paths


def test_icon_resource_present():
    assert paths.icon_path().exists()


def test_icon_renders(qtbot):  # qtbot ensures a QApplication exists
    icon = QIcon(str(paths.icon_path()))
    assert not icon.isNull()
    assert not icon.pixmap(QSize(64, 64)).isNull()
