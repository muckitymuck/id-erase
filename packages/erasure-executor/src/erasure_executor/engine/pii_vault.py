from __future__ import annotations

import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class PIIVault:
    """Encrypted storage for PII profiles using AES-256-GCM."""

    def __init__(self, encryption_key: bytes):
        if len(encryption_key) != 32:
            raise ValueError("Encryption key must be 32 bytes (256-bit)")
        self._aesgcm = AESGCM(encryption_key)

    @classmethod
    def from_hex(cls, hex_key: str) -> PIIVault:
        """Create a vault from a 64-character hex string."""
        key_bytes = bytes.fromhex(hex_key)
        return cls(key_bytes)

    def encrypt(self, profile_data: dict) -> tuple[bytes, bytes, bytes]:
        """Encrypt profile data. Returns (ciphertext, iv, tag)."""
        plaintext = json.dumps(profile_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        iv = os.urandom(12)  # 96-bit nonce for AES-GCM
        ciphertext_with_tag = self._aesgcm.encrypt(iv, plaintext, None)
        # AESGCM appends a 16-byte tag
        ct = ciphertext_with_tag[:-16]
        tag = ciphertext_with_tag[-16:]
        return ct, iv, tag

    def decrypt(self, ciphertext: bytes, iv: bytes, tag: bytes) -> dict:
        """Decrypt and return PII profile dict."""
        combined = ciphertext + tag
        plaintext = self._aesgcm.decrypt(iv, combined, None)
        return json.loads(plaintext.decode("utf-8"))

    @staticmethod
    def data_hash(profile_data: dict) -> str:
        """SHA-256 hash for change detection without decryption."""
        canonical = json.dumps(profile_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
