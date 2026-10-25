# PyInstaller spec: a onedir build (TheraNote.app on macOS), so Qt's LGPL libraries stay
# replaceable. NER models are never bundled; users download them in the app.
# Build with packaging/build_dmg.sh or packaging/build_appimage.sh.
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "src"))
from datafuzzy.ot import APP_NAME  # noqa: E402  the one definition of the app's name

SLUG = APP_NAME.lower()
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
# Info.plist versions are up to three integers; the branch scheme's 5-part version is
# kept in the file names and in the package metadata.
PLIST_VERSION = ".".join(VERSION.split(".")[:3])
PKG = ROOT / "src" / "datafuzzy"

# The key store: keyring finds its backends through entry points and imports them by name,
# so neither shows up in the import graph. macOS also needs LocalAuthentication for the
# Touch ID / password check before the Keychain is read.
if sys.platform == "darwin":
    key_imports = (collect_submodules("keyring.backends") + collect_submodules("LocalAuthentication")
                   + collect_submodules("objc") + collect_submodules("Foundation"))
else:
    key_imports = (collect_submodules("keyring.backends") + collect_submodules("secretstorage")
                   # Jeepney wheels include tests that would pull pytest into the app.
                   + collect_submodules("jeepney", filter=lambda name: "tests" not in name.split(".")))

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(PKG / "models_manifest.json"), "datafuzzy"),
        (str(PKG / "icon.png"), "datafuzzy"),
        (str(PKG / "ot" / "icon.png"), "datafuzzy/ot"),
        (str(PKG / "ot" / "excel_template.xlsx"), "datafuzzy/ot"),
        (str(PKG / "ot" / "ui" / "calendar.png"), "datafuzzy/ot/ui"),
        (str(PKG / "ot" / "ui" / "calendar@2x.png"), "datafuzzy/ot/ui"),
        (str(PKG / "ot" / "ui" / "clock.png"), "datafuzzy/ot/ui"),
        (str(PKG / "ot" / "ui" / "clock@2x.png"), "datafuzzy/ot/ui"),
        (str(PKG / "ot" / "ui" / "place.png"), "datafuzzy/ot/ui"),
        (str(PKG / "ot" / "ui" / "place@2x.png"), "datafuzzy/ot/ui"),
        (str(PKG / "given_names.txt"), "datafuzzy"),
        (str(ROOT / "LICENSE"), "datafuzzy"),
        (str(ROOT / "build" / "THIRD_PARTY_LICENSES.txt"), "datafuzzy"),
        *copy_metadata("datafuzzy"),  # __version__ comes from package metadata
        *copy_metadata("keyring"),    # its backends are listed in its entry points
    ],
    hiddenimports=key_imports,
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
    name=SLUG if sys.platform != "darwin" else APP_NAME,
    console=False,
    upx=False,
    target_arch=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(PKG / "ot" / "icon.png"),  # converted to .icns (needs Pillow)
        bundle_identifier=f"io.github.aquilawei.{SLUG}",
        version=PLIST_VERSION,
        info_plist={
            "CFBundleShortVersionString": PLIST_VERSION,
            "CFBundleVersion": PLIST_VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "14.0",  # onnxruntime wheels need macOS 14
            "NSHumanReadableCopyright": "GPL-3.0-or-later",
        },
    )
