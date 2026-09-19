# PyInstaller spec: a onedir build (DataFuzzy.app on macOS), so Qt's LGPL libraries stay
# replaceable. NER models are never bundled; users download them in the app.
# Build with packaging/build_dmg.sh or packaging/build_appimage.sh.
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH).parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
PKG = ROOT / "src" / "datafuzzy"

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(PKG / "models_manifest.json"), "datafuzzy"),
        (str(PKG / "icon.png"), "datafuzzy"),
        (str(ROOT / "LICENSE"), "datafuzzy"),
        (str(ROOT / "build" / "THIRD_PARTY_LICENSES.txt"), "datafuzzy"),
        *copy_metadata("datafuzzy"),  # __version__ comes from package metadata
    ],
    # tokenizers only needs these for Hub downloads, which the app never does.
    excludes=["tkinter", "huggingface_hub", "hf_xet", "httpx", "fsspec", "tqdm", "yaml"],
    noarchive=False,
)

# Qt plugins the app doesn't use, and what only they pull in: the GTK theme (bundling the
# build machine's GTK breaks against the user's), the virtual keyboard (Qt Quick) and PDF.
DROP = ("qgtk3", "qtvirtualkeyboard", "qpdf", "Qt6Quick", "Qt6Qml", "Qt6Pdf",
        "Qt6VirtualKeyboard", "libgtk-3", "libgdk-3", "libgdk_pixbuf", "libatk", "libatspi",
        "libcairo-gobject", "libcloudproviders", "libepoxy", "libtinysparql", "libjson-glib",
        "libglycin", "Qt/translations")
a.binaries = [b for b in a.binaries if not any(d in b[0] for d in DROP)]
a.datas = [d for d in a.datas if not any(x in d[0] for x in DROP)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="datafuzzy" if sys.platform != "darwin" else "DataFuzzy",
    console=False,
    upx=False,
    target_arch=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="DataFuzzy", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="DataFuzzy.app",
        icon=str(PKG / "icon.png"),  # converted to .icns (needs Pillow)
        bundle_identifier="io.github.aquilawei.datafuzzy",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "14.0",  # onnxruntime wheels need macOS 14
            "NSHumanReadableCopyright": "GPL-3.0-or-later",
        },
    )
