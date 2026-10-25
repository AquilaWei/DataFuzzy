from datetime import date

import pytest
from keyring.errors import KeyringError

from datafuzzy.ot.db import RecordStore, write_meta
from datafuzzy.ot.keys import (
    AuthenticatedKeyProvider,
    KeyringKeyProvider,
    KeyUnavailable,
    PasswordKeyProvider,
    UnlockCancelled,
    UnlockFailed,
    default_provider,
    keyring_available,
    raise_for_reply,
)


class FakeKeyring:
    """Stands in for the `keyring` module, so no real keychain is touched."""

    def __init__(self, priority=5, error=None):
        self.passwords = {}
        self.priority = priority
        self.error = error

    def get_password(self, service, user):
        if self.error:
            raise self.error
        return self.passwords.get((service, user))

    def set_password(self, service, user, password):
        self.passwords[(service, user)] = password

    def get_keyring(self):
        if isinstance(self.priority, Exception):
            raise self.priority
        return self


class FakeLaError:
    def __init__(self, code):
        self._code = code

    def code(self):
        return self._code

    def localizedDescription(self):
        return "fake"


class RecordingProvider:
    def __init__(self):
        self.calls = 0

    def get_key(self):
        self.calls += 1
        return bytes(32)


def password_asker(*answers):
    """Returns answers in order and records what it was asked as (creating, retry)."""
    asked = []
    remaining = iter(answers)

    def ask(creating, retry):
        asked.append((creating, retry))
        return next(remaining)

    ask.asked = asked
    return ask


# --- keyring ---------------------------------------------------------------------------


def test_first_launch_creates_a_256_bit_key_in_the_keyring():
    backend = FakeKeyring()
    key = KeyringKeyProvider(allow_create=True, backend=backend).get_key()
    assert len(key) == 32
    assert len(backend.passwords) == 1


def test_second_launch_gets_the_same_key():
    backend = FakeKeyring()
    first = KeyringKeyProvider(allow_create=True, backend=backend).get_key()
    assert KeyringKeyProvider(allow_create=False, backend=backend).get_key() == first


def test_missing_keyring_entry_for_existing_database_raises_without_creating_a_key():
    backend = FakeKeyring()
    with pytest.raises(KeyUnavailable):
        KeyringKeyProvider(allow_create=False, backend=backend).get_key()
    assert backend.passwords == {}


def test_keyring_error_raises_unlock_failed():
    with pytest.raises(UnlockFailed):
        KeyringKeyProvider(allow_create=True, backend=FakeKeyring(error=KeyringError("locked"))).get_key()


def test_damaged_keyring_entry_raises_key_unavailable():
    backend = FakeKeyring()
    backend.set_password("TheraNote", "database-key", "c2hvcnQ=")  # 5 bytes
    with pytest.raises(KeyUnavailable):
        KeyringKeyProvider(allow_create=False, backend=backend).get_key()


def test_keyring_with_positive_priority_is_available():
    assert keyring_available(FakeKeyring(priority=5)) is True


def test_keyring_placeholder_with_zero_priority_is_not_available():
    assert keyring_available(FakeKeyring(priority=0)) is False


def test_keyring_that_cannot_run_here_is_not_available():
    assert keyring_available(FakeKeyring(priority=RuntimeError("no dbus"))) is False


# --- macOS authentication --------------------------------------------------------------


def test_cancelled_authentication_never_reads_the_key():
    inner = RecordingProvider()

    def cancel(reason):
        raise UnlockCancelled("cancelled")

    with pytest.raises(UnlockCancelled):
        AuthenticatedKeyProvider(inner, cancel).get_key()
    assert inner.calls == 0


def test_failed_authentication_never_reads_the_key():
    inner = RecordingProvider()

    def refuse(reason):
        raise UnlockFailed("refused")

    with pytest.raises(UnlockFailed):
        AuthenticatedKeyProvider(inner, refuse).get_key()
    assert inner.calls == 0


def test_successful_authentication_returns_the_key():
    inner = RecordingProvider()
    assert AuthenticatedKeyProvider(inner, lambda reason: None).get_key() == bytes(32)
    assert inner.calls == 1


def test_authentication_reason_names_the_app():
    reasons = []
    AuthenticatedKeyProvider(RecordingProvider(), reasons.append).get_key()
    assert reasons == ["Unlock TheraNote"]


def test_successful_reply_does_not_raise():
    raise_for_reply(True, None)


@pytest.mark.parametrize("code", [-2, -4, -9])
def test_user_system_or_app_cancel_reply_raises_cancelled(code):
    with pytest.raises(UnlockCancelled):
        raise_for_reply(False, FakeLaError(code))


def test_other_failure_reply_raises_unlock_failed():
    with pytest.raises(UnlockFailed):
        raise_for_reply(False, FakeLaError(-1))


# --- password fallback -----------------------------------------------------------------


def test_first_password_prompt_asks_to_create_one(tmp_path):
    ask = password_asker("hunter2")
    PasswordKeyProvider(tmp_path / "t.db", ask).get_key()
    assert ask.asked == [(True, False)]


def test_same_password_derives_the_same_key_next_time(tmp_path):
    first = PasswordKeyProvider(tmp_path / "t.db", password_asker("hunter2")).get_key()
    again = PasswordKeyProvider(tmp_path / "t.db", password_asker("hunter2")).get_key()
    assert again == first


def test_later_prompt_asks_for_existing_password(tmp_path):
    PasswordKeyProvider(tmp_path / "t.db", password_asker("hunter2")).get_key()
    ask = password_asker("hunter2")
    PasswordKeyProvider(tmp_path / "t.db", ask).get_key()
    assert ask.asked == [(False, False)]


def test_wrong_password_is_asked_again_then_right_one_unlocks(tmp_path):
    first = PasswordKeyProvider(tmp_path / "t.db", password_asker("hunter2")).get_key()
    ask = password_asker("wrong", "hunter2")
    assert PasswordKeyProvider(tmp_path / "t.db", ask).get_key() == first
    assert ask.asked == [(False, False), (False, True)]


def test_cancelling_password_prompt_raises_cancelled(tmp_path):
    PasswordKeyProvider(tmp_path / "t.db", password_asker("hunter2")).get_key()
    with pytest.raises(UnlockCancelled):
        PasswordKeyProvider(tmp_path / "t.db", password_asker(None)).get_key()


def test_empty_password_is_asked_again_when_creating(tmp_path):
    ask = password_asker("", "hunter2")
    PasswordKeyProvider(tmp_path / "t.db", ask).get_key()
    assert ask.asked == [(True, False), (True, True)]


def test_different_passwords_give_different_keys(tmp_path):
    a = PasswordKeyProvider(tmp_path / "a.db", password_asker("one")).get_key()
    b = PasswordKeyProvider(tmp_path / "b.db", password_asker("two")).get_key()
    assert a != b


def test_password_fallback_unlocks_data_after_reopening(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, PasswordKeyProvider(path, password_asker("hunter2")).get_key()) as store:
        student = store.add_student("王小明")
        store.add_record(student.id, date(2026, 10, 1), "新竹國小", "中文版")
    with RecordStore(path, PasswordKeyProvider(path, password_asker("hunter2")).get_key()) as again:
        assert again.records_for_student(student.id)[0].zh_text == "中文版"


def test_password_is_not_stored_in_database_file(tmp_path):
    path = tmp_path / "t.db"
    PasswordKeyProvider(path, password_asker("hunter2-secret")).get_key()
    assert b"hunter2-secret" not in path.read_bytes()


# --- choosing a provider ---------------------------------------------------------------


def test_new_linux_database_with_keyring_uses_keyring(tmp_path):
    provider = default_provider(tmp_path / "t.db", password_asker(), platform="linux", backend=FakeKeyring())
    assert isinstance(provider, KeyringKeyProvider)


def test_new_linux_database_without_keyring_falls_back_to_password(tmp_path):
    provider = default_provider(tmp_path / "t.db", password_asker(), platform="linux",
                                backend=FakeKeyring(priority=0))
    assert isinstance(provider, PasswordKeyProvider)


def test_database_protected_by_password_stays_on_password_even_if_keyring_appears(tmp_path):
    path = tmp_path / "t.db"
    PasswordKeyProvider(path, password_asker("hunter2")).get_key()
    provider = default_provider(path, password_asker(), platform="linux", backend=FakeKeyring())
    assert isinstance(provider, PasswordKeyProvider)


def test_keyring_database_without_keyring_raises_instead_of_switching_to_password(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, bytes(32)):
        pass
    with pytest.raises(KeyUnavailable):
        default_provider(path, password_asker(), platform="linux", backend=FakeKeyring(priority=0))


def test_macos_provider_requires_authentication(tmp_path):
    provider = default_provider(tmp_path / "t.db", password_asker(), platform="darwin",
                                backend=FakeKeyring(), authenticate=lambda reason: None)
    assert isinstance(provider, AuthenticatedKeyProvider)


def test_macos_cancelled_authentication_leaves_keyring_untouched(tmp_path):
    backend = FakeKeyring()

    def cancel(reason):
        raise UnlockCancelled("cancelled")

    provider = default_provider(tmp_path / "t.db", password_asker(), platform="darwin",
                                backend=backend, authenticate=cancel)
    with pytest.raises(UnlockCancelled):
        provider.get_key()
    assert backend.passwords == {}


def test_existing_database_does_not_get_a_new_keyring_key(tmp_path):
    path = tmp_path / "t.db"
    write_meta(path, "key_check", b"x")  # a database that was initialised before
    backend = FakeKeyring()
    provider = default_provider(path, password_asker(), platform="linux", backend=backend)
    with pytest.raises(KeyUnavailable):
        provider.get_key()
    assert backend.passwords == {}
