import os

import pytest

from datafuzzy.ot.crypto import Cipher, DecryptionError


def test_round_trip_returns_original_text():
    cipher = Cipher(os.urandom(32))
    assert cipher.decrypt(cipher.encrypt("王小明 practiced", "student.name"), "student.name") == "王小明 practiced"


def test_ciphertext_does_not_contain_plaintext():
    cipher = Cipher(os.urandom(32))
    assert "王小明".encode() not in cipher.encrypt("王小明", "student.name")


def test_same_text_encrypts_differently_each_time():
    cipher = Cipher(os.urandom(32))
    assert cipher.encrypt("abc", "x") != cipher.encrypt("abc", "x")


def test_wrong_key_raises_decryption_error():
    blob = Cipher(os.urandom(32)).encrypt("secret", "x")
    with pytest.raises(DecryptionError):
        Cipher(os.urandom(32)).decrypt(blob, "x")


def test_other_context_raises_decryption_error():
    cipher = Cipher(os.urandom(32))
    with pytest.raises(DecryptionError):
        cipher.decrypt(cipher.encrypt("secret", "record.zh_text"), "record.en_text")


def test_tampered_ciphertext_raises_decryption_error():
    cipher = Cipher(os.urandom(32))
    blob = bytearray(cipher.encrypt("secret", "x"))
    blob[-1] ^= 1
    with pytest.raises(DecryptionError):
        cipher.decrypt(bytes(blob), "x")


def test_truncated_ciphertext_raises_decryption_error():
    with pytest.raises(DecryptionError):
        Cipher(os.urandom(32)).decrypt(b"short", "x")


def test_key_of_wrong_length_is_rejected():
    with pytest.raises(ValueError):
        Cipher(b"too short")
