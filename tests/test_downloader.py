import threading

import pytest

from datafuzzy.core.models import (
    ChecksumError,
    DownloadCancelled,
    delete_model,
    download_model,
    is_installed,
    load_manifest,
)
from datafuzzy.core.models.manifest import FileSpec, ModelSpec


def test_download_and_install(file_server, tmp_path):
    spec = file_server.spec()
    seen = []
    assert not is_installed(spec, tmp_path)
    download_model(spec, tmp_path, progress=lambda d, t: seen.append((d, t)))
    assert is_installed(spec, tmp_path)
    assert (tmp_path / "fake/b.txt").read_bytes() == b"hello"
    assert seen[-1] == (spec.size, spec.size)
    assert not list(tmp_path.glob("fake/*.part"))


def test_resume_from_partial_file(file_server, tmp_path):
    spec = file_server.spec()
    data = file_server.files["/fake/a.bin"]
    (tmp_path / "fake").mkdir()
    (tmp_path / "fake/a.bin.part").write_bytes(data[:1000])
    download_model(spec, tmp_path)
    assert ("/fake/a.bin", "bytes=1000-") in file_server.requests
    assert (tmp_path / "fake/a.bin").read_bytes() == data


def test_server_without_range_restarts(file_server, tmp_path):
    spec = file_server.spec()
    file_server.support_range = False
    (tmp_path / "fake").mkdir()
    (tmp_path / "fake/a.bin.part").write_bytes(b"x" * 1000)
    download_model(spec, tmp_path)
    assert is_installed(spec, tmp_path)


def test_checksum_mismatch_deletes_file(file_server, tmp_path):
    spec = file_server.spec()
    file_server.files["/fake/b.txt"] = b"HELLO"  # same size, different content
    with pytest.raises(ChecksumError):
        download_model(spec, tmp_path)
    assert not (tmp_path / "fake/b.txt.part").exists()
    assert not is_installed(spec, tmp_path)


def test_cancel_keeps_partial_for_resume(file_server, tmp_path):
    spec = file_server.spec()
    cancel = threading.Event()

    def progress(done, total):
        if done > 0:
            cancel.set()

    with pytest.raises(DownloadCancelled):
        download_model(spec, tmp_path, progress, cancel)
    assert (tmp_path / "fake/a.bin.part").exists()
    assert not is_installed(spec, tmp_path)
    download_model(spec, tmp_path)
    assert is_installed(spec, tmp_path)


def test_new_manifest_version_needs_redownload(file_server, tmp_path):
    spec = file_server.spec()
    download_model(spec, tmp_path)
    changed = ModelSpec(spec.id, spec.lang, spec.name, spec.source, spec.license, spec.labels,
                        (spec.files[0], FileSpec("b.txt", spec.files[1].url, 5, "0" * 64)))
    assert not is_installed(changed, tmp_path)


def test_delete(file_server, tmp_path):
    spec = file_server.spec()
    download_model(spec, tmp_path)
    delete_model(spec, tmp_path)
    assert not (tmp_path / "fake").exists()


def test_bundled_manifest():
    specs = load_manifest()
    assert {s.lang for s in specs} >= {"en"}
    for s in specs:
        assert s.labels and s.license
        names = {f.name for f in s.files}
        assert {"model.onnx", "tokenizer.json", "config.json"} <= names
        for f in s.files:
            assert f.url.startswith("https://") and len(f.sha256) == 64 and f.size > 0
