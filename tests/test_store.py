import os
import subprocess
import sys

import pytest
from cryptography.exceptions import InvalidTag

from datafuzzy.core.mapping import Session
from datafuzzy.core.store import SessionStore, sweep_stale


def test_save_load_encrypted(tmp_path):
    store = SessionStore(tmp_path)
    s = store.new_session()
    s.code_for("alice@example.com", "EMAIL")
    store.save(s)
    raw = (store.dir / f"{s.id}.dfmap").read_bytes()
    assert b"alice" not in raw
    assert store.load(s.id).to_code == {"alice@example.com": "[EMAIL_A]"}


def test_other_key_cannot_decrypt(tmp_path):
    a = SessionStore(tmp_path)
    s = a.new_session()
    b = SessionStore(tmp_path)  # same pid -> same dir, different key
    with pytest.raises(InvalidTag):
        b.load(s.id)


def test_cleanup_removes_dir(tmp_path):
    store = SessionStore(tmp_path)
    store.new_session()
    store.new_session()
    assert len(list(store.dir.iterdir())) == 2
    store.cleanup()
    assert not store.dir.exists()
    assert store.list() == []
    store.cleanup()  # idempotent


def test_sweep_removes_dead_process_dirs(tmp_path):
    proc = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, text=True, check=True)
    dead = tmp_path / f"datafuzzy-{proc.stdout.strip()}"
    dead.mkdir()
    (dead / "x.dfmap").write_bytes(b"junk")
    alive = tmp_path / f"datafuzzy-{os.getppid()}"
    alive.mkdir()
    other = tmp_path / "datafuzzy-notapid"
    other.mkdir()

    removed = sweep_stale(tmp_path)

    assert dead in removed and not dead.exists()
    assert alive.exists() and other.exists()


def test_session_dict_round_trip():
    s = Session(label="x")
    s.code_for("a", "PERSON")
    assert Session.from_dict(s.to_dict()) == s
