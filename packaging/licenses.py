"""Write THIRD_PARTY_LICENSES.txt for the packages bundled into the app, and fail if any of
them has a license that can't be combined with GPL-3.0.

Usage: uv run --group package packaging/licenses.py [output]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement

# Substrings that mark a license as incompatible with distributing the app under GPL-3.0.
FORBIDDEN = ("GPL-2.0-only", "GPLv2 only", "GPL-2.0 only", "Proprietary", "Commercial",
             "AGPL", "SSPL", "BUSL", "CC-BY-NC")
TEXTS = Path(__file__).parent / "license-texts"
# Wheels that ship no license file: the standard text of the license we use them under.
FALLBACK = {
    "PySide6": "LGPL-3.0-only", "PySide6_Addons": "LGPL-3.0-only",
    "PySide6_Essentials": "LGPL-3.0-only", "shiboken6": "LGPL-3.0-only",
    "tokenizers": "Apache-2.0", "flatbuffers": "Apache-2.0",
}


def compatible(license_: str) -> bool:
    """A dual-licensed package ("LGPL-3.0-only OR GPL-2.0-only") is fine if any choice is."""
    if "UNKNOWN" in license_:
        return False
    return any(not any(f.lower() in choice.lower() for f in FORBIDDEN)
               for choice in re.split(r"\s+OR\s+", license_))


def runtime_closure(root: str = "datafuzzy") -> list[str]:
    """Names of every distribution the app needs at runtime (no dev/extra requirements)."""
    seen: dict[str, str] = {}
    todo = [root]
    while todo:
        dist = distribution(todo.pop())
        key = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
        if key in seen:
            continue
        seen[key] = dist.metadata["Name"]
        for req in map(Requirement, dist.requires or []):
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                todo.append(req.name)
    return sorted(name for key, name in seen.items() if key != root)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/THIRD_PARTY_LICENSES.txt")
    names = runtime_closure()
    raw = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json", "--from=mixed",
         "--with-urls", "--with-license-file", "--with-notice-file", "--no-license-path",
         "--packages", *names],
        check=True, capture_output=True, text=True).stdout
    pkgs = sorted({p["Name"]: p for p in json.loads(raw)}.values(), key=lambda p: p["Name"].lower())
    if missing := set(names) - {p["Name"] for p in pkgs}:
        raise SystemExit(f"no license info for: {sorted(missing)}")

    bad = []
    parts = [
        "DataFuzzy is licensed under GPL-3.0-or-later. It bundles the following packages,\n"
        "each under its own license. NER models are not bundled; they are downloaded by the\n"
        "user and carry their own licenses (see the model manager).\n",
    ]
    for p in pkgs:
        license_ = p["License"]
        print(f"{p['Name']:28} {p['Version']:12} {license_}")
        if not compatible(license_):
            bad.append(f"{p['Name']}: {license_}")
        parts.append("=" * 78 + f"\n{p['Name']} {p['Version']}\nLicense: {license_}\n"
                     f"URL: {p['URL']}\n" + "=" * 78 + "\n")
        texts = [p[k].strip() for k in ("LicenseText", "NoticeText") if p.get(k, "UNKNOWN") != "UNKNOWN"]
        if not texts and p["Name"] in FALLBACK:
            texts = [(TEXTS / f"{FALLBACK[p['Name']]}.txt").read_text().strip()]
        if not texts:
            bad.append(f"{p['Name']}: no license text")
        parts += [t + "\n" for t in texts]
    if bad:
        raise SystemExit("licenses not compatible with GPL-3.0 (or unknown):\n  " + "\n  ".join(bad))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts))
    print(f"wrote {out} ({len(pkgs)} packages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
