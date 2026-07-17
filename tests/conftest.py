"""Keep tests out of the real user config.

The app persists harmonic rules, notation and window geometry through
QSettings("keydup", "keydup"). Tests construct the widgets that read and
write those, so without isolation a run picks up whatever the developer
has saved - a customised harmonic rule set fails test_filters - and
clobbers it on the way out.

Both formats get redirected: that two-argument constructor resolves to
NativeFormat regardless of setDefaultFormat(), so redirecting IniFormat
alone silently misses. On Windows native settings live in the registry
and ignore setPath, but nothing there reads them back within a run.
"""

import pytest
from PySide6.QtCore import QSettings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("settings"))
    for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
        QSettings.setPath(fmt, QSettings.UserScope, root)
