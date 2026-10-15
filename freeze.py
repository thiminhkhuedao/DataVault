import json
import os
import hashlib
import getpass
from datetime import datetime

HISTORY_FILE = ".datavault/history.json"
FREEZE_FILE  = ".datavault/frozen.json"
SIGNING_FILE = ".datavault/signatures.json"


def freeze_version(filepath, version_id, reason="", method="password"):
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

    frozen = _load_frozen()
    key    = f"{filename}__{version_id}"

    if key in frozen:
        f_at = frozen[key]["frozen_at"][:19].replace("T", " ")
        f_by = frozen[key]["frozen_by"]
        return False, (
            f"'{filename}' {version_id} is already frozen.\n"
            f"  Frozen by: {f_by} on {f_at}\n"
            f"  Reason: {frozen[key].get('reason', '—')}"
        )

    frozen_at = datetime.now().isoformat()
    frozen_by = os.getenv("USERNAME") or os.getenv("USER") or "unknown"

    entry = {
        "filename":   filename,
        "version_id": version_id,
        "file_hash":  target["hash"],
        "frozen_at":  frozen_at,
        "frozen_by":  frozen_by,
        "reason":     reason or "No reason provided",
        "method":     method,
    }

    if method == "password":
        print(f"\n  Set a passphrase to protect this freeze.")
        print(f"  Without it, nobody can unfreeze '{filename}' {version_id}.\n")
        pw1 = getpass.getpass("  Passphrase: ")
        pw2 = getpass.getpass("  Confirm:    ")
        if pw1 != pw2:
            return False, "Passphrases do not match. Freeze cancelled."
        if len(pw1) < 4:
            return False, "Passphrase too short (minimum 4 characters). Freeze cancelled."
        salt    = os.urandom(32).hex()
        pw_hash = hashlib.pbkdf2_hmac("sha256", pw1.encode(), salt.encode(), 200_000).hex()
        entry["pw_hash"] = pw_hash
        entry["pw_salt"] = salt
        method_note = "Protected by passphrase (PBKDF2-SHA256)"

    elif method == "signature":
        method_note = "Protected by owner signature"
    else:
        return False, f"Unknown method '{method}'. Use 'password' or 'signature'."

    frozen[key] = entry
    _save_frozen(frozen)

    return True, (
        f"Frozen '{filename}' {version_id}\n"
        f"  By:       {frozen_by}\n"
        f"  At:       {frozen_at[:19].replace('T', ' ')}\n"
        f"  Hash:     {target['hash'][:32]}...\n"
        f"  Reason:   {reason or 'No reason provided'}\n"
        f"  Security: {method_note}\n\n"
        f"  This version is now locked."
    )


def unfreeze_version(filepath, version_id, reason="", requester=None):
    filename = os.path.basename(filepath)
    frozen   = _load_frozen()
    key      = f"{filename}__{version_id}"

    if key not in frozen:
        return False, f"'{filename}' {version_id} is not frozen."

    entry  = frozen[key]
    method = entry.get("method", "password")

    if method == "password":
        if "pw_hash" not in entry:
            return False, "Freeze record is missing password hash. Cannot unfreeze safely."
        print(f"\n  '{filename}' {version_id} is frozen with a passphrase.\n")
        pw = getpass.getpass("  Passphrase: ")
        pw_hash = hashlib.pbkdf2_hmac(
            "sha256", pw.encode(), entry["pw_salt"].encode(), 200_000
        ).hex()
        if pw_hash != entry["pw_hash"]:
            return False, "Incorrect passphrase. Unfreeze denied."
        unfreeze_by = os.getenv("USERNAME") or os.getenv("USER") or "unknown"

    elif method == "signature":
        if not os.path.exists(SIGNING_FILE):
            return False, (
                f"No signatures found for {version_id}.\n"
                f"  Sign as owner first:\n"
                f"  python datavault.py sign {filepath} {version_id} <name> owner"
            )
        with open(SIGNING_FILE, "r", encoding="utf-8") as f:
            sigs = json.load(f)
        version_sigs = sigs.get(filename, {}).get(version_id, [])
        owners = [s["signer"] for s in version_sigs if s["role"] == "owner"]

        if not owners:
            return False, (
                f"Cannot unfreeze — no owner signature on {version_id}.\n"
                f"  Sign as owner first:\n"
                f"  python datavault.py sign {filepath} {version_id} <name> owner"
            )
        if requester and requester not in owners:
            return False, (
                f"Cannot unfreeze — '{requester}' is not an owner of {version_id}.\n"
                f"  Current owners: {', '.join(owners)}"
            )
        unfreeze_by = requester or owners[0]
    else:
        return False, f"Unknown freeze method '{method}'."

    frozen.pop(key)
    _save_frozen(frozen)

    return True, (
        f"Unfrozen '{filename}' {version_id}\n"
        f"  Authorized by:    {unfreeze_by}\n"
        f"  Originally frozen by: {entry['frozen_by']} "
        f"on {entry['frozen_at'][:19].replace('T', ' ')}\n"
        f"  Reason: {reason or 'No reason provided'}\n\n"
        f"  You can now commit new versions of '{filename}'."
    )


def check_frozen(filename, version_id=None):
    frozen = _load_frozen()
    if version_id:
        key = f"{filename}__{version_id}"
        return key in frozen, frozen.get(key)
    file_frozen = {k: v for k, v in frozen.items() if v["filename"] == filename}
    return len(file_frozen) > 0, file_frozen


def list_frozen():
    frozen = _load_frozen()
    if not frozen:
        return True, "No frozen versions."

    all_sigs = {}
    if os.path.exists(SIGNING_FILE):
        with open(SIGNING_FILE, "r", encoding="utf-8") as f:
            all_sigs = json.load(f)

    lines = ["\nFrozen versions:\n" + "─" * 55]
    for key, entry in frozen.items():
        f_at   = entry["frozen_at"][:19].replace("T", " ")
        method = entry.get("method", "password")
        if method == "password":
            security = "passphrase protected"
        else:
            version_sigs = all_sigs.get(entry["filename"], {}).get(entry["version_id"], [])
            owners       = [s["signer"] for s in version_sigs if s["role"] == "owner"]
            security     = f"owner signature — {', '.join(owners) if owners else 'none (unfreeze blocked)'}"

        lines.append(
            f"\n  {entry['filename']} {entry['version_id']}\n"
            f"  Frozen by: {entry['frozen_by']} on {f_at}\n"
            f"  Reason:    {entry.get('reason', '—')}\n"
            f"  Security:  {security}"
        )
    lines.append(f"\n{'─' * 55}")
    lines.append(f"  {len(frozen)} frozen version(s)")
    return True, "\n".join(lines)


def is_frozen(filename, version_id):
    frozen = _load_frozen()
    return f"{filename}__{version_id}" in frozen


def _load_frozen():
    if os.path.exists(FREEZE_FILE):
        with open(FREEZE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_frozen(data):
    os.makedirs(os.path.dirname(FREEZE_FILE), exist_ok=True)
    with open(FREEZE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)