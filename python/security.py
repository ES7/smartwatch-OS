# =============================================================================
#  security.py — Security Manager
# =============================================================================
#
#  REAL OS CONCEPT:
#  Security in embedded OS has three layers:
#
#  1. SECURE BOOT — verify kernel hasn't been tampered with before running it.
#     Real implementation: ROM bootloader checks cryptographic signature of
#     the kernel image using a public key burned into the chip at factory.
#     If signature fails → refuse to boot. This prevents malicious firmware.
#
#  2. ENCRYPTED STORAGE — sensitive data (health records, payment tokens)
#     stored encrypted on flash. Even if someone physically reads the flash
#     chip, they get gibberish without the key.
#     Real implementation: AES-256 encryption, key stored in ARM TrustZone
#     secure enclave — a separate CPU core that normal code can't access.
#
#  3. APP VERIFICATION — before running a third-party app, verify it was
#     signed by a trusted developer. Prevents malicious apps.
#     Real implementation: public-key cryptography (RSA or ECC).
#     Same system Apple/Google use for App Store apps.
#
#  Our simulation uses Python's hashlib for hashing and a simple XOR
#  cipher (educational — real systems use AES-256 + proper key management).
# =============================================================================

import hashlib
import hmac
import time
import json
import os


# ── Crypto Primitives ─────────────────────────────────────────────────────────

class Crypto:
    """
    Cryptographic utilities.
    Educational XOR cipher + SHA-256 hashing.
    Real OS: replaced with hardware AES accelerator + mbedTLS library.
    """

    # Master key — in real OS this lives in TrustZone secure enclave
    # NEVER hardcode in production. This is for simulation only.
    _MASTER_KEY = b"AJXOS_SecureKey_2024_DoNotUse!!"

    @staticmethod
    def sha256(data: bytes) -> str:
        """Hash data with SHA-256. Like a fingerprint — same input = same hash."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def hmac_sign(data: bytes, key: bytes = None) -> str:
        """
        HMAC-SHA256 signature.
        Like SHA-256 but requires knowing the secret key to verify.
        Used for: kernel image signing, session tokens, app verification.
        """
        key = key or Crypto._MASTER_KEY
        return hmac.new(key, data, hashlib.sha256).hexdigest()

    @staticmethod
    def encrypt(plaintext: str, key: bytes = None) -> bytes:
        """
        XOR stream cipher (educational only — use AES in production).
        Key is repeated to match plaintext length, then XORed byte by byte.
        """
        key     = key or Crypto._MASTER_KEY
        data    = plaintext.encode("utf-8")
        key_rep = (key * (len(data) // len(key) + 1))[:len(data)]
        return bytes(a ^ b for a, b in zip(data, key_rep))

    @staticmethod
    def decrypt(ciphertext: bytes, key: bytes = None) -> str:
        """XOR is symmetric — decrypt = encrypt."""
        key     = key or Crypto._MASTER_KEY
        key_rep = (key * (len(ciphertext) // len(key) + 1))[:len(ciphertext)]
        plain   = bytes(a ^ b for a, b in zip(ciphertext, key_rep))
        return plain.decode("utf-8")

    @staticmethod
    def verify_hmac(data: bytes, signature: str, key: bytes = None) -> bool:
        """Verify a signature without timing attacks (constant-time compare)."""
        expected = Crypto.hmac_sign(data, key)
        return hmac.compare_digest(expected, signature)


# ── Secure Boot ───────────────────────────────────────────────────────────────

class SecureBoot:
    """
    Verifies OS integrity before kernel starts.
    Real: ROM bootloader does this in hardware before RAM is even initialized.
    Ours: runs during Stage 1 of boot, checks file hashes.
    """

    # Known-good hashes (in real OS: stored in write-protected flash region)
    TRUSTED_HASHES = {}   # populated at first boot (factory provisioning)

    @staticmethod
    def provision(files: list):
        """
        Factory provisioning — compute and store trusted hashes.
        Real: done in secure factory environment, hashes burned to OTP flash.
        """
        for path in files:
            try:
                with open(path, "rb") as f:
                    content = f.read()
                SecureBoot.TRUSTED_HASHES[path] = Crypto.sha256(content)
            except FileNotFoundError:
                pass

    @staticmethod
    def verify(files: list) -> dict:
        """
        Verify files match trusted hashes.
        Returns dict of {file: "OK"/"TAMPERED"/"UNKNOWN"}.
        """
        results = {}
        for path in files:
            try:
                with open(path, "rb") as f:
                    content = f.read()
                current_hash = Crypto.sha256(content)
                trusted_hash = SecureBoot.TRUSTED_HASHES.get(path)
                if trusted_hash is None:
                    results[path] = "UNKNOWN"
                elif current_hash == trusted_hash:
                    results[path] = "OK"
                else:
                    results[path] = "TAMPERED"
            except FileNotFoundError:
                results[path] = "MISSING"
        return results


# ── Encrypted Storage ─────────────────────────────────────────────────────────

class SecureStorage:
    """
    Encrypted key-value store for sensitive data.
    Uses VFS underneath but encrypts values before writing.

    Real use cases:
      - Health data (heart rate history, sleep records)
      - Payment tokens (contactless pay credentials)
      - User credentials (Wi-Fi passwords, API keys)
    """

    def __init__(self, vfs_ref, base_path="/data/secure"):
        self._vfs  = vfs_ref
        self._path = base_path
        try:
            self._vfs.mkdir(base_path)
        except Exception:
            pass
        self._audit_log = []

    def write(self, key: str, value: str, owner_pid: int = 0):
        """Encrypt and store a value."""
        encrypted = Crypto.encrypt(value)
        signature = Crypto.hmac_sign(encrypted)

        record = {
            "data":      list(encrypted),   # bytes → list for JSON
            "signature": signature,
            "written":   time.time(),
            "owner_pid": owner_pid,
        }

        path = f"{self._path}/{self._sanitize(key)}.sec"
        self._vfs.write_json(path, record)

        self._audit("WRITE", key, owner_pid)

    def read(self, key: str, caller_pid: int = 0) -> str:
        """Decrypt and return a value. Verifies integrity before returning."""
        path = f"{self._path}/{self._sanitize(key)}.sec"
        try:
            record    = self._vfs.read_json(path)
            encrypted = bytes(record["data"])
            signature = record["signature"]

            # Verify integrity — detect tampering
            if not Crypto.verify_hmac(encrypted, signature):
                self._audit("INTEGRITY_FAIL", key, caller_pid)
                raise SecurityError(f"Integrity check failed for '{key}'")

            # Check ownership (simple — real OS uses proper ACLs)
            if record["owner_pid"] != 0 and record["owner_pid"] != caller_pid:
                self._audit("ACCESS_DENIED", key, caller_pid)
                raise SecurityError(f"Access denied: '{key}' owned by pid {record['owner_pid']}")

            self._audit("READ", key, caller_pid)
            return Crypto.decrypt(encrypted)

        except FileNotFoundError:
            raise KeyError(f"Secure key not found: '{key}'")

    def delete(self, key: str):
        """Securely delete — overwrite with zeros first, then unlink."""
        path = f"{self._path}/{self._sanitize(key)}.sec"
        # Overwrite with zeros (prevents data recovery from flash)
        try:
            stat = self._vfs.stat(path)
            fd   = self._vfs.open(path, "w")
            self._vfs.write(fd, b"\x00" * stat["size"])
            self._vfs.close(fd)
            self._vfs.unlink(path)
        except Exception:
            pass

    def _sanitize(self, key: str) -> str:
        """Remove path traversal chars — prevent directory traversal attacks."""
        return key.replace("/", "_").replace("..", "_").replace("\\", "_")

    def _audit(self, action: str, key: str, pid: int):
        """Audit log — who accessed what and when."""
        self._audit_log.append({
            "action": action,
            "key":    key,
            "pid":    pid,
            "time":   time.strftime("%H:%M:%S"),
        })

    def audit_log(self) -> list:
        return self._audit_log[-20:]


# ── App Verifier ──────────────────────────────────────────────────────────────

class AppVerifier:
    """
    Verifies third-party apps before allowing them to run.
    Real: RSA-2048 or ECC signature verification using developer certificate.
    Ours: HMAC simulation (conceptually identical).
    """

    TRUSTED_DEVELOPERS = {
        "ajx_official": Crypto.hmac_sign(b"ajx_official"),
        "dev_mode":      Crypto.hmac_sign(b"dev_mode"),
    }

    @staticmethod
    def sign_app(app_name: str, app_code: str, developer: str) -> dict:
        """Simulate signing an app (done by developer, not on watch)."""
        payload   = f"{app_name}:{app_code}".encode()
        signature = Crypto.hmac_sign(payload)
        return {
            "app":       app_name,
            "developer": developer,
            "signature": signature,
            "signed_at": time.time(),
        }

    @staticmethod
    def verify_app(app_name: str, app_code: str, manifest: dict) -> bool:
        """Verify app signature before installation/execution."""
        payload   = f"{app_name}:{app_code}".encode()
        expected  = Crypto.hmac_sign(payload)
        return hmac.compare_digest(expected, manifest.get("signature", ""))


# ── Custom Exceptions ─────────────────────────────────────────────────────────

class SecurityError(Exception):
    pass


# ── Security Manager ──────────────────────────────────────────────────────────

class SecurityManager:
    """Top-level security coordinator. Kernel holds one instance."""

    def __init__(self, vfs_ref):
        self.secure_boot    = SecureBoot()
        self.secure_storage = SecureStorage(vfs_ref)
        self.app_verifier   = AppVerifier()
        self._threat_log    = []

    def log_threat(self, threat_type: str, details: str):
        entry = {
            "type":    threat_type,
            "details": details,
            "time":    time.strftime("%H:%M:%S"),
        }
        self._threat_log.append(entry)

    def threat_log(self) -> list:
        return self._threat_log
