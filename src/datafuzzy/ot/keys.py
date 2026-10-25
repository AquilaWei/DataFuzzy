"""Where the database key comes from, and what must happen before it is handed out.

A `KeyProvider` returns the 256-bit key or raises `UnlockError`; nothing in the database is
read until it has. The core never imports Qt: a password is asked through a callback.

- macOS: the system must authenticate the user (Touch ID or login password) before the
  key is read from the Keychain.
- Linux: the key lives in the Secret Service (via `keyring`); with no usable backend the
  key is derived from a password the user chooses.
"""

from __future__ import annotations

import base64
import os
import queue
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import keyring
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from keyring.errors import KeyringError

from . import APP_NAME
from .crypto import KEY_BYTES, Cipher, DecryptionError
from .db import read_meta, write_meta

KEYRING_SERVICE = APP_NAME
KEYRING_USER = "database-key"

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
PASSWORD_CHECK_TEXT = "password-check"

# LocalAuthentication LAError codes that mean "the user (or system) backed out".
LA_CANCEL_CODES = {-2, -4, -9}  # user cancel, system cancel, app cancel


class UnlockError(Exception):
    """The key could not be obtained; the database must stay closed."""


class UnlockCancelled(UnlockError):
    """The user dismissed the authentication or password prompt."""


class UnlockFailed(UnlockError):
    """Authentication was refused, or the system could not perform it."""


class KeyUnavailable(UnlockError):
    """The database exists but its key cannot be found (e.g. the keychain entry is gone).
    A new key is never made up: it could not open the existing data."""


class KeyProvider(Protocol):
    def get_key(self) -> bytes:
        """The 32-byte database key. May block while the user answers a prompt, so call it
        where blocking is acceptable. Raises UnlockError."""


class KeyringKeyProvider:
    """A random key kept in the system keyring (macOS Keychain, Secret Service...)."""

    def __init__(self, allow_create: bool, backend=keyring) -> None:
        """`allow_create` is True only for a database that does not exist yet; otherwise a
        missing entry raises KeyUnavailable instead of replacing the key."""
        self._allow_create = allow_create
        self._backend = backend

    def get_key(self) -> bytes:
        try:
            stored = self._backend.get_password(KEYRING_SERVICE, KEYRING_USER)
            if stored is None:
                if not self._allow_create:
                    raise KeyUnavailable(f"no {APP_NAME} key in the system keyring")
                stored = base64.b64encode(os.urandom(KEY_BYTES)).decode()
                self._backend.set_password(KEYRING_SERVICE, KEYRING_USER, stored)
        except KeyringError as e:
            raise UnlockFailed(f"system keyring refused access: {e}") from e
        key = base64.b64decode(stored)
        if len(key) != KEY_BYTES:
            raise KeyUnavailable("the key in the system keyring is damaged")
        return key


def keyring_available(backend=keyring) -> bool:
    """Whether the system has a real keyring (not keyring's fail/null placeholder)."""
    try:
        return backend.get_keyring().priority > 0
    except RuntimeError:  # keyring raises this for a backend that cannot run here
        return False


def raise_for_reply(success: bool, error) -> None:
    """Turn the answer of LAContext.evaluatePolicy into the matching UnlockError."""
    if success:
        return
    if error is not None and error.code() in LA_CANCEL_CODES:
        raise UnlockCancelled("authentication cancelled")
    raise UnlockFailed(f"authentication failed: {error.localizedDescription() if error else 'unknown'}")


def system_authenticate(reason: str) -> None:
    """Ask macOS to verify the user with Touch ID or the login password.

    Blocks until the user answers. Raises UnlockCancelled or UnlockFailed. Only runs on
    macOS (pyobjc-framework-LocalAuthentication)."""
    from LocalAuthentication import LAContext, LAPolicyDeviceOwnerAuthentication

    context = LAContext.alloc().init()
    can_evaluate, error = context.canEvaluatePolicy_error_(LAPolicyDeviceOwnerAuthentication, None)
    if not can_evaluate:
        raise UnlockFailed(f"this Mac cannot authenticate: {error}")
    replies: queue.Queue = queue.Queue()  # the reply block runs on a system thread
    context.evaluatePolicy_localizedReason_reply_(
        LAPolicyDeviceOwnerAuthentication, reason, lambda success, err: replies.put((success, err)))
    raise_for_reply(*replies.get())


class AuthenticatedKeyProvider:
    """Requires `authenticate` to succeed before `inner` is even asked for the key."""

    def __init__(self, inner: KeyProvider, authenticate: Callable[[str], None] = system_authenticate) -> None:
        self._inner = inner
        self._authenticate = authenticate

    def get_key(self) -> bytes:
        self._authenticate(f"Unlock {APP_NAME}")
        return self._inner.get_key()


class PasswordKeyProvider:
    """A key derived (scrypt) from a password the user chooses, for systems without a
    keyring. The salt and a password check are kept in the database file; the key and the
    password never are."""

    def __init__(self, db_path: Path, ask_password: Callable[[bool, bool], str | None]) -> None:
        """`ask_password(creating, retry)` returns the password, or None if the user cancels.
        `creating` is True the first time (choose a password), `retry` after a wrong or
        empty one."""
        self._path = db_path
        self._ask = ask_password

    def get_key(self) -> bytes:
        salt = read_meta(self._path, "password_salt")
        check = read_meta(self._path, "password_check")
        creating = salt is None or check is None
        if creating:
            salt = os.urandom(SALT_BYTES)
        retry = False
        while True:
            password = self._ask(creating, retry)
            if password is None:
                raise UnlockCancelled("password entry cancelled")
            retry = True
            if not password:
                continue
            key = Scrypt(salt=salt, length=KEY_BYTES, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(password.encode())
            if creating:
                write_meta(self._path, "password_salt", salt)
                write_meta(self._path, "password_check", Cipher(key).encrypt(PASSWORD_CHECK_TEXT, "meta.password_check"))
                return key
            try:
                Cipher(key).decrypt(check, "meta.password_check")
            except DecryptionError:
                continue
            return key


def default_provider(db_path: Path, ask_password: Callable[[bool, bool], str | None], *,
                     platform: str = sys.platform, backend=keyring,
                     authenticate: Callable[[str], None] = system_authenticate) -> KeyProvider:
    """The provider this database and this system call for.

    A database already protected by a password stays on the password; a database made with
    a keyring key never switches to a password (it could not open the data), it raises
    KeyUnavailable if the keyring is gone. Only a new database on a Linux without a keyring
    starts on a password. macOS always uses the Keychain behind system authentication."""
    if read_meta(db_path, "password_salt") is not None:
        return PasswordKeyProvider(db_path, ask_password)
    new_database = read_meta(db_path, "key_check") is None
    keyring_key = KeyringKeyProvider(allow_create=new_database, backend=backend)
    if platform == "darwin":
        return AuthenticatedKeyProvider(keyring_key, authenticate)
    if keyring_available(backend):
        return keyring_key
    if new_database:
        return PasswordKeyProvider(db_path, ask_password)
    raise KeyUnavailable("the database key is in the system keyring, which is not available")
