"""Wheel + filter composition tests (offscreen)."""

from PySide6.QtCore import QPointF, Qt

from keydup.domain import Track
from keydup.ui.camelot_wheel import CamelotWheel
from keydup.ui.filter_bar import FilterBar
from keydup.ui.track_table import TrackFilterProxy, TrackTableModel


def make_track(i, key, bpm, artist="X"):
    return Track(
        id=i, folder_id=1, path=f"/m/{i}.mp3", filename=f"{i}.mp3",
        artist=artist, title=f"t{i}", bpm=bpm, key_camelot=key, status="done",
    )


def make_proxy():
    model = TrackTableModel()
    model.set_tracks([
        make_track(1, "8A", 128),
        make_track(2, "7A", 140),
        make_track(3, "9A", 126, artist="findme"),
        make_track(4, "8B", 128),
        make_track(5, "3B", 174),
        make_track(6, None, None),  # unanalyzed
    ])
    proxy = TrackFilterProxy()
    proxy.setSourceModel(model)
    return proxy


def visible_keys(proxy):
    return {
        proxy.sourceModel().tracks[proxy.mapToSource(proxy.index(r, 0)).row()].key_camelot
        for r in range(proxy.rowCount())
    }


def test_harmonic_filter_composition(qtbot):
    proxy = make_proxy()
    bar = FilterBar(proxy)
    qtbot.addWidget(bar)

    bar.wheel.set_selected(frozenset({"8A"}))
    assert visible_keys(proxy) == {"8A"}

    bar.harmonic.setChecked(True)
    assert visible_keys(proxy) == {"8A", "7A", "9A", "8B"}
    assert bar.wheel._harmonic_preview == frozenset({"7A", "9A", "8B"})

    # stacks with BPM range
    bar.bpm.setValue((120, 130))
    assert visible_keys(proxy) == {"8A", "9A", "8B"}

    # and with text
    proxy.set_text("findme")
    assert visible_keys(proxy) == {"9A"}

    bar.clear_all()
    proxy.set_text("")
    assert proxy.rowCount() == 6


def test_bpm_full_span_means_no_filter(qtbot):
    proxy = make_proxy()
    bar = FilterBar(proxy)
    qtbot.addWidget(bar)
    bar.bpm.setValue((60, 200))
    assert proxy.rowCount() == 5  # all analyzed tracks pass; unanalyzed (None) excluded
    bar.bpm.setValue((55, 215))
    assert proxy.rowCount() == 6  # full span readmits the unanalyzed track


def test_wheel_click_toggles(qtbot):
    wheel = CamelotWheel()
    wheel.resize(300, 300)
    qtbot.addWidget(wheel)
    wheel._rebuild_paths()

    # click the center of the 8B wedge path
    target = wheel._paths["8B"].boundingRect().center()
    # boundingRect center of an arc wedge may fall outside the path; nudge via label position
    target = wheel._label_rect("8B").center()
    assert wheel._key_at(QPointF(target)) == "8B"

    qtbot.mouseClick(wheel, Qt.LeftButton, pos=target.toPoint())
    assert wheel.selected() == frozenset({"8B"})
    qtbot.mouseClick(wheel, Qt.LeftButton, pos=target.toPoint())
    assert wheel.selected() == frozenset()
