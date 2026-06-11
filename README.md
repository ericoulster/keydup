# key'd up

DJ library manager built on [keypipe](https://github.com/ericoulster/Keypipe):
scan folders of music, detect key (Camelot) and BPM with keypipe's
KeyNet + TempoCNN pipeline, tag tracks by genre or DJ set, and search by
text, an interactive Camelot wheel (with harmonic matching), and BPM
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

## How analysis works

Detection is keypipe's, unchanged: KeyNet CNN over a CQT spectrogram
for key (Camelot notation), TempoCNN plus onset-assisted correction for
BPM. Results, confidences, and the backend used are stored per track;
re-analysis is queued automatically when the file changes on disk or
the analysis version is bumped. Files renamed outside the app (e.g. by
the keypipe CLI's filename tagging) are re-matched by size + duration
fingerprint so tags and analysis survive.
