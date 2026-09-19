"""Resumable, checksum-verified model downloads (the app's only network access)."""

from __future__ import annotations

import hashlib
import json
import shutil
import ssl
import threading
import urllib.request
from collections.abc import Callable
from pathlib import Path

import certifi

from .manifest import ModelSpec

CHUNK = 1 << 20
MARKER = ".installed"

Progress = Callable[[int, int], None]  # (bytes done, bytes total)


class DownloadCancelled(Exception):
    pass


class ChecksumError(Exception):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _marker_content(spec: ModelSpec) -> str:
    return json.dumps({f.name: f.sha256 for f in spec.files}, sort_keys=True)


def is_installed(spec: ModelSpec, root: Path) -> bool:
    """Installed = verified download of exactly this manifest version."""
    marker = root / spec.id / MARKER
    try:
        return marker.read_text() == _marker_content(spec) and all(
            (root / spec.id / f.name).stat().st_size == f.size for f in spec.files
        )
    except OSError:
        return False


def delete_model(spec: ModelSpec, root: Path) -> None:
    shutil.rmtree(root / spec.id, ignore_errors=True)


def download_model(
    spec: ModelSpec,
    root: Path,
    progress: Progress | None = None,
    cancel: threading.Event | None = None,
) -> Path:
    dest = root / spec.id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / MARKER).unlink(missing_ok=True)
    ctx = ssl.create_default_context(cafile=certifi.where())
    total = spec.size
    done = 0

    for f in spec.files:
        target = dest / f.name
        if target.exists() and target.stat().st_size == f.size and _sha256(target) == f.sha256:
            done += f.size
            continue
        part = dest / (f.name + ".part")
        offset = part.stat().st_size if part.exists() else 0
        if offset > f.size:
            part.unlink()
            offset = 0

        req = urllib.request.Request(f.url, headers={"User-Agent": "DataFuzzy"})
        if offset:
            req.add_header("Range", f"bytes={offset}-")
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            if offset and resp.status != 206:  # server ignored Range: start over
                offset = 0
            with part.open("ab" if offset else "wb") as out:
                done += offset
                if progress:
                    progress(done, total)
                while chunk := resp.read(CHUNK):
                    if cancel is not None and cancel.is_set():
                        raise DownloadCancelled(spec.id)  # keep .part for resuming
                    out.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)

        if _sha256(part) != f.sha256:
            part.unlink()
            raise ChecksumError(f"{spec.id}/{f.name}")
        part.replace(target)

    (dest / MARKER).write_text(_marker_content(spec))
    return dest
