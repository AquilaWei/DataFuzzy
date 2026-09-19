"""Regenerate src/datafuzzy/models_manifest.json from pinned Hugging Face revisions.

    uv run tools/update_manifest.py

Downloads each file once (cached in models/cache/) to record its size and SHA-256.
Bump a model by changing its `revision` below and re-running.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "models/cache"
MANIFEST = ROOT / "src/datafuzzy/models_manifest.json"

MODELS = [
    {
        "id": "en-bert-ner",
        "lang": "en",
        "name": "English NER (BERT base, int8)",
        "source": "dslim/bert-base-NER",
        "license": "MIT",
        "labels": {"PER": "PERSON", "ORG": "ORG", "LOC": "LOC"},
        "repo": "Xenova/bert-base-NER",
        "revision": "8e892123e8b7c2c0c2bd1dcb598b7d244c4e53aa",
        # local name -> path in repo
        "files": {
            "model.onnx": "onnx/model_quantized.onnx",
            "tokenizer.json": "tokenizer.json",
            "config.json": "config.json",
        },
    },
]


def fetch(url: str, dest: Path) -> Path:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(url) as resp, tmp.open("wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
        tmp.replace(dest)
    return dest


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    out = []
    for m in MODELS:
        files = []
        for name, remote in m["files"].items():
            url = f"https://huggingface.co/{m['repo']}/resolve/{m['revision']}/{remote}"
            path = fetch(url, CACHE / m["id"] / name)
            files.append({"name": name, "url": url, "size": path.stat().st_size, "sha256": sha256(path)})
            print(f"{m['id']}/{name}: {path.stat().st_size / 1e6:.1f} MB")
        entry = {k: m[k] for k in ("id", "lang", "name", "source", "license", "labels")}
        entry["files"] = files
        out.append(entry)
    MANIFEST.write_text(json.dumps({"models": out}, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
