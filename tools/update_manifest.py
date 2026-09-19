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
        "id": "privacy-filter",
        "kind": "privacy-filter",
        "lang": "any",
        "name": "個資偵測 (OpenAI Privacy Filter, q4)",
        "source": "openai/privacy-filter",
        "license": "Apache-2.0",
        "labels": {
            "private_person": "PERSON", "private_address": "LOC", "private_date": "DATE",
            "private_email": "EMAIL", "private_phone": "PHONE", "private_url": "URL",
            "account_number": "ID", "secret": "SECRET",
        },
        "repo": "openai/privacy-filter",
        "revision": "7ffa9a043d54d1be65afb281eddf0ffbe629385b",
        # The graph refers to its weights as "model_q4.onnx_data": keep that name.
        "files": {
            "model.onnx": "onnx/model_q4.onnx",
            "model_q4.onnx_data": "onnx/model_q4.onnx_data",
            "tokenizer.json": "tokenizer.json",
            "config.json": "config.json",
        },
    },
    {
        "id": "zh-bert-ner",
        "kind": "ner",
        "lang": "zh",
        "name": "中文人名 (CKIP BERT base, int8)",
        "source": "ckiplab/bert-base-chinese-ner",
        "license": "GPL-3.0",
        # Chinese people only: the privacy filter finds everything else.
        "labels": {"PERSON": "PERSON"},
        "repo": "Xenova/bert-base-chinese-ner",
        "revision": "be592940bc954f32492c831bdd1d086a04036597",
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
        entry = {k: m[k] for k in ("id", "kind", "lang", "name", "source", "license", "labels")}
        entry["files"] = files
        out.append(entry)
    MANIFEST.write_text(json.dumps({"models": out}, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
