# key'd up

DJ library manager built on [keypipe](https://github.com/ericoulster/keypipe):
scan folders of music, detect key and BPM with keypipe's
KeyNet + TempoCNN pipeline, tag tracks by genre or DJ set, and search by
text, an interactive key wheel (with harmonic matching), and BPM
range. Built-in playback and reveal-in-file-manager. Fully offline -
everything lives in a local SQLite database; your audio files are never
modified.

## Running from source

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and a sibling
checkout of keypipe (the path dependency in `pyproject.toml` expects
`../keypipe`):

```
uv sync
uv run keydup
```

GPU (CUDA) is used automatically for key detection when available;
everything also works CPU-only.

## Using the app

**Build a library.** Toolbar > Add Folder picks a music folder; files
appear in the table within seconds (metadata pass), then key/BPM fill
in as background analysis completes. Analysis resumes automatically if
you close the app mid-run, and Rescan picks up new/changed files -
renamed files keep their tags via a size+duration fingerprint match.

**Find music.** The search box matches artist/title/filename. The
Filters dock has the key wheel (click wedges to filter; multi-select
works), a harmonic-matches toggle - the gear next to it configures
which moves count, e.g. the diagonal and +7 energy-boost mixes - and a
BPM range slider. Check tags in the Tags dock to filter by them. All
filters stack.

**Play.** Double-click a row (or press Space with the table focused).
The waveform at the bottom shows progress; click or drag on it to
seek. Right-click a row for Play / Reveal in file manager / Tags /
Re-analyze.

**Tags and sets.** Create genres and sets with the buttons in the Tags
dock, assign via a row's right-click > Tags menu (works on
multi-selection). Sets are ordered playlists: check exactly one set in
the Tags dock and the table switches to its order (# column) - drag
rows to rearrange, or use the context menu's Move up/down. Right-click
a set > "Export set to folder" copies its files into a directory as
"01 Track.mp3", "02 ..." so the order survives on USB sticks and CDJs;
originals are never touched.

**Display.** Drag column headers to rearrange the table. View > Key
notation switches how keys are written (Open Key by default). Window
layout, column order, and all settings persist between runs.

Library data lives in `~/.local/share/keydup/library.db` (Linux),
`~/Library/Application Support/keydup/` (macOS) - delete it to start
fresh; your audio files are never modified.

## Platform notes

- **Linux / macOS**: fully supported (BPM detection needs essentia,
  which ships wheels for both; macOS arm64 wheels require macOS 15+).
- **Windows**: not yet - essentia has no Windows wheels. The BPM backend
  sits behind an interface so a future ONNX TempoCNN port can enable a
  Windows build without quality loss.
- **macOS Gatekeeper**: release bundles are not signed/notarized. First
  launch: right-click the app, choose Open, confirm - or
  `xattr -dr com.apple.quarantine "key'd up.app"`.

## Development

```
QT_QPA_PLATFORM=offscreen uv run pytest tests -q   # full suite, headless
uv run pyinstaller packaging/keydup.spec --noconfirm
./dist/keydup/keydup --self-test
```

Releases build from CI (`.github/workflows/build.yml`) on tag push
(`v*`): Linux tar.gz + macOS .app zip.

## Key notation

Keys display in **Open Key** notation by default (1d-12d major,
1m-12m minor - the open standard used by Beatport and Traktor).
View > Key notation switches to 1A-12B wheel numbers, classical key
names, or a custom mapping: picking Custom creates an editable
`notation.json` next to the library database with one label per key.

## How analysis works

Detection is keypipe's, unchanged: KeyNet CNN over a CQT spectrogram
for key, TempoCNN plus onset-assisted correction for
BPM. The TempoCNN weights (deepsquare-k16, Schreiber & Mueller) come
from the [Essentia models](https://essentia.upf.edu/models.html)
collection (MTG-UPF) and are licensed CC BY-NC-SA 4.0 - keydup is free
and non-commercial; commercial use of the models would need a separate
license from MTG. Results, confidences, and the backend used are stored per track;
re-analysis is queued automatically when the file changes on disk or
the analysis version is bumped. Files renamed outside the app (e.g. by
the keypipe CLI's filename tagging) are re-matched by size + duration
fingerprint so tags and analysis survive.
