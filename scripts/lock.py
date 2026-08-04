"""
Passphrase gate for a site with no backend.

A static host cannot check a password — anything the browser can test, an
attacker can skip. The only honest gate is to never serve the plaintext: the
build encrypts the rendered app and ships ciphertext, and the browser derives
the key from a passphrase you type and decrypts it locally. Fetch app.enc
without the passphrase and you get noise.

AES-256-GCM, key from PBKDF2-HMAC-SHA256 with a fresh salt every build.
Set SITE_PASSPHRASE as a repository secret to switch it on; leave it unset and
the site builds exactly as before.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os

ITERATIONS = 210_000
SALT_BYTES = 16
IV_BYTES = 12


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def available() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        return True
    except Exception:
        return False


def new_salt() -> bytes:
    """One salt per build, shared by every encrypted file.

    The browser derives the key once at unlock and must be able to open the
    side-files too — a per-file salt means a per-file key, and the dossier
    silently failed to decrypt. The IV is still unique per file, which is what
    GCM actually requires.
    """
    return os.urandom(SALT_BYTES)


def encrypt(plaintext: str, passphrase: str, iterations: int = ITERATIONS,
            salt: bytes | None = None) -> dict:
    """Return a JSON-serialisable envelope the browser's Web Crypto can open."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt = salt or os.urandom(SALT_BYTES)
    iv = os.urandom(IV_BYTES)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32)
    ct = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    return {"v": 1, "kdf": "PBKDF2-SHA256", "iter": iterations,
            "salt": _b64(salt), "iv": _b64(iv), "ct": _b64(ct)}


def write_encrypted(path: str, plaintext: str, passphrase: str,
                    salt: bytes | None = None) -> int:
    env = encrypt(plaintext, passphrase, salt=salt)
    with open(path, "w") as f:
        json.dump(env, f, separators=(",", ":"))
    return len(env["ct"])
