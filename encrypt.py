import hashlib
import hmac
import json
import os
import base64
import struct
from datetime import datetime

HISTORY_FILE  = ".datavault/history.json"
VERSIONS_DIR  = ".datavault/versions"
KEYSTORE_FILE = ".datavault/keystore.json"
ENCRYPTED_DIR = ".datavault/encrypted"


# ── Key management ────────────────────────────────────────────

def generate_key(key_name, passphrase):
    """
    Derive a symmetric encryption key from a passphrase using PBKDF2.
    Stores only the key metadata (name, salt, hash) — never the key itself.
    Also generates a one-time recovery code in case the passphrase is forgotten.
    """
    salt     = os.urandom(32)
    key      = _derive_key(passphrase, salt)
    key_hash = hashlib.sha256(key).hexdigest()

    keystore = _load_keystore()
    if key_name in keystore:
        return False, f"Key '{key_name}' already exists. Use a different name or delete it first."

    # Generate recovery code: DV-XXXX-XXXX-XXXX-XXXX
    raw_code     = os.urandom(16).hex().upper()
    recovery_code = f"DV-{raw_code[0:4]}-{raw_code[4:8]}-{raw_code[8:12]}-{raw_code[12:16]}"
    recovery_salt = os.urandom(32)
    recovery_hash = hashlib.pbkdf2_hmac(
        "sha256", recovery_code.encode("utf-8"), recovery_salt, 200_000
    ).hex()

    keystore[key_name] = {
        "name":          key_name,
        "salt":          base64.b64encode(salt).decode(),
        "key_hash":      key_hash,
        "created_at":    datetime.now().isoformat(),
        "created_by":    os.getenv("USERNAME") or os.getenv("USER") or "unknown",
        "recovery_hash": recovery_hash,
        "recovery_salt": base64.b64encode(recovery_salt).decode(),
        "recovery_used": False
    }
    _save_keystore(keystore)

    return True, (
        f"Key '{key_name}' created.\n"
        f"  Key hash: {key_hash[:24]}...\n\n"
        f"  ┌─────────────────────────────────────────────┐\n"
        f"  │  RECOVERY CODE — save this somewhere safe   │\n"
        f"  │                                             │\n"
        f"  │  {recovery_code}              │\n"
        f"  │                                             │\n"
        f"  │  One-time use only. Cannot be regenerated. │\n"
        f"  └─────────────────────────────────────────────┘\n\n"
        f"  If you forget your passphrase:\n"
        f"  python datavault.py recover {key_name}"
    )


def recover_key(key_name, recovery_code, new_passphrase):
    """
    Reset a key's passphrase using the one-time recovery code.
    The recovery code is invalidated after use.
    """
    keystore = _load_keystore()

    if key_name not in keystore:
        return False, f"Key '{key_name}' not found."

    entry = keystore[key_name]

    if entry.get("recovery_used"):
        return False, (
            f"Recovery code for '{key_name}' has already been used.\n"
            f"  If you no longer have access, the encrypted versions\n"
            f"  cannot be recovered. Create a new key with 'keygen'."
        )

    if "recovery_hash" not in entry:
        return False, f"Key '{key_name}' has no recovery code (created before this feature)."

    # Normalize code — remove dashes and spaces, uppercase
    code_clean    = recovery_code.replace("-", "").replace(" ", "").upper()
    code_formatted = f"DV-{code_clean[0:4]}-{code_clean[4:8]}-{code_clean[8:12]}-{code_clean[12:16]}" if len(code_clean) == 16 else recovery_code

    recovery_salt = base64.b64decode(entry["recovery_salt"])
    submitted_hash = hashlib.pbkdf2_hmac(
        "sha256", code_formatted.encode("utf-8"), recovery_salt, 200_000
    ).hex()

    if submitted_hash != entry["recovery_hash"]:
        return False, "Invalid recovery code."

    if len(new_passphrase) < 4:
        return False, "New passphrase too short (minimum 4 characters)."

    # Set new passphrase
    new_salt     = os.urandom(32)
    new_key      = _derive_key(new_passphrase, new_salt)
    new_key_hash = hashlib.sha256(new_key).hexdigest()

    entry["salt"]          = base64.b64encode(new_salt).decode()
    entry["key_hash"]      = new_key_hash
    entry["recovery_used"] = True
    entry["recovered_at"]  = datetime.now().isoformat()

    # Re-encrypt all files with new key
    old_key     = None  # Can't re-encrypt without old passphrase
    reencrypted = 0

    # Note: we can't re-encrypt existing files since we don't have the old key
    # The recovery only resets the passphrase for future encrypt/decrypt operations
    # Existing encrypted files need to be re-encrypted manually with the new passphrase

    _save_keystore(keystore)

    return True, (
        f"Passphrase reset for key '{key_name}'.\n"
        f"  Recovery code invalidated — cannot be used again.\n"
        f"  New key hash: {new_key_hash[:24]}...\n\n"
        f"  ⚠ Existing encrypted files were created with the old key.\n"
        f"  They cannot be decrypted with the new passphrase.\n"
        f"  If you still have the old passphrase, decrypt them first,\n"
        f"  then re-encrypt with: python datavault.py encrypt <file> <v> {key_name}"
    )


def encrypt_version(filepath, version_id, key_name, passphrase):
    """
    Encrypt a specific version of a file with the given key.
    The encrypted file is stored in .datavault/encrypted/
    The original stored version is NOT deleted — encryption is additive.
    """
    filename = os.path.basename(filepath)

    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions = history["files"][filename]["versions"]
    target   = next((v for v in versions if v["version_id"] == version_id), None)
    if not target:
        available = ", ".join(v["version_id"] for v in versions)
        return False, f"Version '{version_id}' not found. Available: {available}"

    # Verify key exists and passphrase is correct
    keystore = _load_keystore()
    if key_name not in keystore:
        return False, f"Key '{key_name}' not found. Create it first with: datavault keygen {key_name}"

    salt = base64.b64decode(keystore[key_name]["salt"])
    key  = _derive_key(passphrase, salt)

    # Verify passphrase
    key_hash = hashlib.sha256(key).hexdigest()
    if key_hash != keystore[key_name]["key_hash"]:
        return False, "Incorrect passphrase."

    # Read the stored version file
    safe_name    = filename.replace("/", "_").replace("\\", "_")
    version_path = os.path.join(VERSIONS_DIR, f"{safe_name}__{version_id}")

    if not os.path.exists(version_path):
        return False, f"Stored file for {version_id} not found. Run 'migrate' first."

    with open(version_path, "rb") as f:
        plaintext = f.read()

    # Home-made stream cipher: keystream = HMAC-SHA256(key, iv || counter),
    # XORed with the data, then authenticated with HMAC-SHA256.
    # NOT AES and NOT independently audited. Fine for local/low-risk data;
    # the SaaS version must use AES-GCM from the 'cryptography' library.
    iv         = os.urandom(16)
    ciphertext = _xor_stream(plaintext, key, iv)
    mac        = hmac.new(key, iv + ciphertext, hashlib.sha256).digest()

    # Pack: magic(4) + version(1) + iv(16) + mac(32) + ciphertext
    MAGIC   = b"DVE1"
    payload = MAGIC + bytes([1]) + iv + mac + ciphertext

    # Save encrypted file
    os.makedirs(ENCRYPTED_DIR, exist_ok=True)
    enc_path = os.path.join(ENCRYPTED_DIR, f"{safe_name}__{version_id}__{key_name}.dvenc")

    with open(enc_path, "wb") as f:
        f.write(payload)

    # Record encryption metadata in history
    if "encrypted" not in target:
        target["encrypted"] = []

    already = any(e["key_name"] == key_name for e in target["encrypted"])
    if not already:
        target["encrypted"].append({
            "key_name":    key_name,
            "encrypted_at": datetime.now().isoformat(),
            "encrypted_by": os.getenv("USERNAME") or os.getenv("USER") or "unknown",
            "enc_file":    enc_path,
            "mac":         mac.hex()[:24]
        })
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

    file_size = len(payload)
    return True, (
        f"Encrypted '{filename}' {version_id} with key '{key_name}'\n"
        f"  Encrypted file: {enc_path}\n"
        f"  Size:           {file_size} bytes\n"
        f"  Algorithm:      HMAC-SHA256 keystream (CTR-style) + HMAC-SHA256 MAC, PBKDF2 key\n"
        f"  MAC:            {mac.hex()[:24]}...\n\n"
        f"  The original version is still in .datavault/versions/\n"
        f"  Only '{key_name}' with the correct passphrase can decrypt this."
    )


def decrypt_version(filepath, version_id, key_name, passphrase, output_path=None):
    """
    Decrypt an encrypted version and write it to output_path
    (or print to stdout if not specified).
    """
    filename  = os.path.basename(filepath)
    safe_name = filename.replace("/", "_").replace("\\", "_")
    enc_path  = os.path.join(ENCRYPTED_DIR, f"{safe_name}__{version_id}__{key_name}.dvenc")

    if not os.path.exists(enc_path):
        return False, f"No encrypted file found for {filename} {version_id} with key '{key_name}'."

    keystore = _load_keystore()
    if key_name not in keystore:
        return False, f"Key '{key_name}' not found."

    salt = base64.b64decode(keystore[key_name]["salt"])
    key  = _derive_key(passphrase, salt)

    if hashlib.sha256(key).hexdigest() != keystore[key_name]["key_hash"]:
        return False, "Incorrect passphrase."

    with open(enc_path, "rb") as f:
        payload = f.read()

    # Unpack
    MAGIC = b"DVE1"
    if payload[:4] != MAGIC:
        return False, "Invalid encrypted file format."

    iv         = payload[5:21]
    mac_stored = payload[21:53]
    ciphertext = payload[53:]

    # Verify MAC before decrypting
    mac_computed = hmac.new(key, iv + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac_stored, mac_computed):
        return False, "MAC verification failed — file may have been tampered with."

    plaintext = _xor_stream(ciphertext, key, iv)

    if output_path:
        with open(output_path, "wb") as f:
            f.write(plaintext)
        return True, (
            f"Decrypted '{filename}' {version_id} → {output_path}\n"
            f"  MAC verified ✓ — content is authentic"
        )
    else:
        try:
            text = plaintext.decode("utf-8")
            return True, f"Decrypted content:\n\n{text}"
        except UnicodeDecodeError:
            return True, f"Decrypted {len(plaintext)} bytes (binary content)"


def rekey(key_name, old_passphrase, new_passphrase):
    """
    Change the passphrase for an existing key.
    Verifies the old passphrase, then re-derives with the new one.
    Encrypted files are not touched — only the keystore is updated.
    """
    keystore = _load_keystore()

    if key_name not in keystore:
        return False, f"Key '{key_name}' not found."

    # Verify old passphrase
    old_salt = base64.b64decode(keystore[key_name]["salt"])
    old_key  = _derive_key(old_passphrase, old_salt)
    if hashlib.sha256(old_key).hexdigest() != keystore[key_name]["key_hash"]:
        return False, "Incorrect old passphrase."

    if len(new_passphrase) < 4:
        return False, "New passphrase too short (minimum 4 characters)."

    if old_passphrase == new_passphrase:
        return False, "New passphrase must be different from the old one."

    # Derive new key with new salt
    new_salt     = os.urandom(32)
    new_key      = _derive_key(new_passphrase, new_salt)
    new_key_hash = hashlib.sha256(new_key).hexdigest()

    keystore[key_name]["salt"]       = base64.b64encode(new_salt).decode()
    keystore[key_name]["key_hash"]   = new_key_hash
    keystore[key_name]["updated_at"] = datetime.now().isoformat()
    _save_keystore(keystore)

    # Re-encrypt all files that used this key with the new key
    reencrypted = 0
    if os.path.exists(ENCRYPTED_DIR):
        for fname in os.listdir(ENCRYPTED_DIR):
            if fname.endswith(f"__{key_name}.dvenc"):
                enc_path = os.path.join(ENCRYPTED_DIR, fname)

                # Decrypt with old key
                with open(enc_path, "rb") as f:
                    payload = f.read()

                MAGIC = b"DVE1"
                if payload[:4] != MAGIC:
                    continue

                iv         = payload[5:21]
                mac_stored = payload[21:53]
                ciphertext = payload[53:]

                mac_computed = hmac.new(old_key, iv + ciphertext, hashlib.sha256).digest()
                if not hmac.compare_digest(mac_stored, mac_computed):
                    continue

                plaintext = _xor_stream(ciphertext, old_key, iv)

                # Re-encrypt with new key
                new_iv         = os.urandom(16)
                new_ciphertext = _xor_stream(plaintext, new_key, new_iv)
                new_mac        = hmac.new(new_key, new_iv + new_ciphertext, hashlib.sha256).digest()
                new_payload    = MAGIC + bytes([1]) + new_iv + new_mac + new_ciphertext

                with open(enc_path, "wb") as f:
                    f.write(new_payload)

                reencrypted += 1

    return True, (
        f"Key '{key_name}' passphrase updated.\n"
        f"  Re-encrypted: {reencrypted} file(s)\n"
        f"  New key hash: {new_key_hash[:24]}...\n"
        f"  Old passphrase no longer works."
    )


def list_encrypted():
    """List all encrypted versions"""
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    lines   = ["\nEncrypted versions:\n" + "─" * 55]
    found   = False

    for filename, data in history["files"].items():
        for v in data["versions"]:
            if v.get("encrypted"):
                found = True
                lines.append(f"\n  {filename} {v['version_id']}")
                for enc in v["encrypted"]:
                    at = enc["encrypted_at"][:19].replace("T", " ")
                    lines.append(f"    key '{enc['key_name']}' — encrypted by {enc['encrypted_by']} on {at}")

    if not found:
        return True, "No encrypted versions. Use 'datavault encrypt <file> <version> <key>' to encrypt."

    keystore = _load_keystore()
    if keystore:
        lines.append(f"\n  Available keys: {', '.join(keystore.keys())}")

    return True, "\n".join(lines)


# ── Crypto primitives (pure Python, no deps) ──────────────────

def _derive_key(passphrase, salt, iterations=200_000):
    """PBKDF2-HMAC-SHA256 key derivation — same as Python's hashlib"""
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, iterations, dklen=32)


def _xor_stream(data, key, iv):
    """
    CTR-style stream cipher using HMAC-SHA256 as the PRF (not AES).
    Generates a keystream by hashing key+iv+counter blocks.
    XORs the keystream with data.
    Slower than AES and not independently audited, but needs zero dependencies.
    """
    output    = bytearray(len(data))
    block_size = 32
    offset     = 0
    counter    = 0

    while offset < len(data):
        # Generate keystream block: HMAC(key, iv || counter)
        counter_bytes = struct.pack(">Q", counter)
        block = hmac.new(key, iv + counter_bytes, hashlib.sha256).digest()

        # XOR with data
        chunk_len = min(block_size, len(data) - offset)
        for i in range(chunk_len):
            output[offset + i] = data[offset + i] ^ block[i]

        offset  += chunk_len
        counter += 1

    return bytes(output)


# ── Storage ───────────────────────────────────────────────────

def _load_keystore():
    if os.path.exists(KEYSTORE_FILE):
        with open(KEYSTORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_keystore(data):
    os.makedirs(os.path.dirname(KEYSTORE_FILE), exist_ok=True)
    with open(KEYSTORE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)