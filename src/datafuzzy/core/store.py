"""Encrypted, process-scoped temp storage for code sessions.

Files live in <tmp>/datafuzzy-<pid>/ and are encrypted with a key that exists only in
this process's memory, so leftovers from a crash are unreadable. The directory is
removed on exit, and stale directories from dead processes are swept at startup.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .mapping import Session

PREFIX = "datafuzzy-"
SUFFIX = ".dfmap"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # exists, owned by someone else
        return True
    return True


def sweep_stale(base: Path | None = None) -> list[Path]:
    """Delete session directories left behind by processes that are no longer running."""
    base = Path(base or tempfile.gettempdir())
    removed: list[Path] = []
    for path in base.glob(PREFIX + "*"):
        suffix = path.name[len(PREFIX):]
        if not path.is_dir() or not suffix.isdigit():
            continue
        pid = int(suffix)
        if pid != os.getpid() and _pid_alive(pid):
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path)
    return removed


class SessionStore:
    def __init__(self, base: Path | None = None) -> None:
        base = Path(base or tempfile.gettempdir())
        self.dir = base / f"{PREFIX}{os.getpid()}"
        self._key = AESGCM.generate_key(bit_length=256)
        self._aead = AESGCM(self._key)
        self.sessions: dict[str, Session] = {}

    def _path(self, session_id: str) -> Path:
        return self.dir / f"{session_id}{SUFFIX}"

    def new_session(self, label: str | None = None) -> Session:
        session = Session(label=label or f"代號檔 {len(self.sessions) + 1}")
        self.save(session)
        return session

    def save(self, session: Session) -> None:
        self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        nonce = os.urandom(12)
        plain = json.dumps(session.to_dict(), ensure_ascii=False).encode()
        blob = nonce + self._aead.encrypt(nonce, plain, session.id.encode())
        path = self._path(session.id)
        path.write_bytes(blob)
        path.chmod(0o600)
        self.sessions[session.id] = session

    def rename(self, session_id: str, label: str) -> None:
        label = label.strip()
        if label:
            session = self.sessions[session_id]
            session.label = label
            self.save(session)

    def load(self, session_id: str) -> Session:
        blob = self._path(session_id).read_bytes()
        plain = self._aead.decrypt(blob[:12], blob[12:], session_id.encode())
        return Session.from_dict(json.loads(plain))

    def list(self) -> list[Session]:
        return sorted(self.sessions.values(), key=lambda s: s.created_at)

    def delete(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)
        self._path(session_id).unlink(missing_ok=True)

    def cleanup(self) -> None:
        """Remove every session file and forget the key. Safe to call more than once."""
        self.sessions.clear()
        shutil.rmtree(self.dir, ignore_errors=True)
        self._key = b""
