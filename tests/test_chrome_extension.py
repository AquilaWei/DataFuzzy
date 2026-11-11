import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
MANIFEST = json.loads((ROOT / "chrome-extension" / "manifest.json").read_text())
APP_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_the_extension_shows_the_app_s_version():
    assert MANIFEST["version_name"] == APP_VERSION


def test_chrome_s_version_is_the_app_s_first_four_numbers():
    # Chrome takes at most four numbers; the full one is in version_name.
    assert MANIFEST["version"] == ".".join(APP_VERSION.split(".")[:4])


def test_every_icon_the_manifest_names_exists():
    icons = list(MANIFEST["icons"].values()) + list(MANIFEST["action"]["default_icon"].values())
    assert [icon for icon in icons if not (ROOT / "chrome-extension" / icon).exists()] == []
