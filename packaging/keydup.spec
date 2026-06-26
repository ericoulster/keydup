# PyInstaller spec for key'd up. Build from the repo root:
#   uv run pyinstaller packaging/keydup.spec --noconfirm
# onedir on purpose: torch makes onefile startup unpacking painfully slow.

import sys
from pathlib import Path

import keypipe

SPEC_DIR = Path(SPECPATH)
ROOT = SPEC_DIR.parent

# Model weights resolved from the installed keypipe package (works for
# editable installs too, unlike collect_data_files).
kp_pkg = Path(keypipe.__file__).parent
datas = [
    (str(kp_pkg / "checkpoints"), "keypipe/checkpoints"),
    (str(kp_pkg / "models"), "keypipe/models"),
    (str(ROOT / "src/keydup/resources"), "keydup/resources"),
]

hiddenimports = ["keypipe.inference_onnx", "onnxruntime"]
# bundles use the ONNX backend everywhere: it beat essentia on the
# benchmark (12/13 vs 9/13), deadlocks nowhere (macOS TF dlopen), and
# drops libtensorflow (~1GB) from the artifact. essentia stays a
# dev-environment dependency for ground-truth comparison only.
excludes_extra = ["essentia"]

a = Analysis(
    [str(ROOT / "src/keydup/__main__.py")],
    pathex=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "torchvision",
        "torchaudio",
        "matplotlib",
        "IPython",
        "tkinter",
        "PyQt5",
        "PyQt6",
    ] + excludes_extra,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="keydup",
    console=False,
)

exes = [exe]
if sys.platform == "win32":
    # console twin for CI self-test and terminal use: windowed exes
    # swallow stdout and surface errors as dialogs on Windows
    exes.append(
        EXE(
            pyz,
            a.scripts,
            [],
            exclude_binaries=True,
            name="keydup-cli",
            console=True,
        )
    )

coll = COLLECT(
    *exes,
    a.binaries,
    a.datas,
    name="keydup",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="key'd up.app",
        bundle_identifier="dev.keydup.keydup",
        version="0.2.0",
    )
