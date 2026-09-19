"""Which models exist, where to get them, and where they live on disk."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from platformdirs import user_data_path

ENV_MODELS_DIR = "DATAFUZZY_MODELS_DIR"


@dataclass(frozen=True)
class FileSpec:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelSpec:
    id: str
    lang: str
    name: str
    source: str
    license: str
    labels: dict[str, str]  # model entity type -> our label, e.g. "PER" -> "PERSON"
    files: tuple[FileSpec, ...]

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)


def load_manifest(path: Path | None = None) -> list[ModelSpec]:
    raw = Path(path).read_text() if path else files("datafuzzy").joinpath("models_manifest.json").read_text()
    return [
        ModelSpec(
            id=m["id"], lang=m["lang"], name=m["name"], source=m["source"],
            license=m["license"], labels=dict(m["labels"]),
            files=tuple(FileSpec(**f) for f in m["files"]),
        )
        for m in json.loads(raw)["models"]
    ]


def models_dir() -> Path:
    """~/Library/Application Support/DataFuzzy/models on macOS, ~/.local/share/... on Linux."""
    override = os.environ.get(ENV_MODELS_DIR)
    return Path(override) if override else user_data_path("DataFuzzy", appauthor=False) / "models"
