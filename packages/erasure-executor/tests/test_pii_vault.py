"""Tests for PII vault encryption/decryption."""

import os
import pytest

from erasure_executor.engine.pii_vault import PIIVault


SAMPLE_PROFILE = {
    "full_name": "Jane Doe",
    "aliases": ["Jane M Doe"],
    "date_of_birth": "1985-03-15",
    "addresses": [{"street": "123 Main St", "city": "Chicago", "state": "IL", "zip": "60601", "current": True}],
    "phone_numbers": [{"number": "+13125551234", "type": "mobile"}],
    "email_addresses": ["jane.doe@example.com"],
    "relatives": ["John Doe"],
}


def _make_vault() -> PIIVault:
    key = os.urandom(32)
    return PIIVault(key)


def test_encrypt_decrypt_roundtrip():
    vault = _make_vault()
    ct, iv, tag = vault.encrypt(SAMPLE_PROFILE)
    result = vault.decrypt(ct, iv, tag)
    assert result == SAMPLE_PROFILE


def test_wrong_key_fails():
    vault1 = PIIVault(os.urandom(32))
    vault2 = PIIVault(os.urandom(32))
    ct, iv, tag = vault1.encrypt(SAMPLE_PROFILE)
    with pytest.raises(Exception):
        vault2.decrypt(ct, iv, tag)


def test_invalid_key_length():
    with pytest.raises(ValueError, match="32 bytes"):
        PIIVault(b"too-short")


def test_data_hash_deterministic():
    vault = _make_vault()
    h1 = vault.data_hash(SAMPLE_PROFILE)
    h2 = vault.data_hash(SAMPLE_PROFILE)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_data_hash_changes_with_data():
    vault = _make_vault()
    h1 = vault.data_hash(SAMPLE_PROFILE)
    modified = {**SAMPLE_PROFILE, "full_name": "John Doe"}
    h2 = vault.data_hash(modified)
    assert h1 != h2


def test_from_hex():
    hex_key = "a" * 64  # 32 bytes as hex
    vault = PIIVault.from_hex(hex_key)
    ct, iv, tag = vault.encrypt({"test": True})
    result = vault.decrypt(ct, iv, tag)
    assert result == {"test": True}


def test_encrypt_produces_different_ciphertext():
    vault = _make_vault()
    ct1, iv1, _ = vault.encrypt(SAMPLE_PROFILE)
    ct2, iv2, _ = vault.encrypt(SAMPLE_PROFILE)
    # Different IVs should produce different ciphertext
    assert iv1 != iv2
