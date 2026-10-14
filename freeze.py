import json
import os
from datetime import datetime

HISTORY_FILE = ".datavault/history.json"
FREEZE_FILE  = ".datavault/frozen.json"
SIGNING_FILE = ".datavault/signatures.json"


def freeze_version(filepath, version_id, reason=""):
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
            f"  Reason: {frozen[key].get('reason', '—')}\n\n"
            f"  Use 'datavault unfreeze {filepath} {version_id}' to unfreeze."
        )

    frozen_at = datetime.now().isoformat()
    frozen_by = os.getenv("USERNAME") or os.getenv("USER") or "unknown"

    frozen[key] = {
        "filename":   filename,
        "version_id": version_id,
        "file_hash":  target["hash"],
        "frozen_at":  frozen_at,
        "frozen_by":  frozen_by,
        "reason":     reason or "No reason provided"
    }

    _save_frozen(frozen)

    return True, (
        f"Frozen '{filename}' {version_id}\n"
        f"  By:     {frozen_by}\n"
        f"  At:     {frozen_at[:19].replace('T', ' ')}\n"
        f"  Hash:   {target['hash'][:32]}...\n"
        f"  Reason: {reason or 'No reason provided'}\n\n"
        f"  This version is now locked. No further commits can be made\n"
        f"  to '{filename}' without unfreezing first.\n"
        f"  To unfreeze: sign as owner first, then run unfreeze."
    )


def unfreeze_version(filepath, version_id, reason="", requester=None):
    filename = os.path.basename(filepath)
    frozen   = _load_frozen()
    key      = f"{filename}__{version_id}"

    if key not in frozen:
        return False, f"'{filename}' {version_id} is not frozen."

    # Require owner signature
    if os.path.exists(SIGNING_FILE):
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
                f"  Current owners: {', '.join(owners)}\n"
                f"  Only an owner can unfreeze."
            )

        unfreeze_by = requester or owners[0]
    else:
        return False, (
            f"Cannot unfreeze — no signatures found for {version_id}.\n"
            f"  Sign as owner first:\n"
            f"  python datavault.py sign {filepath} {version_id} <name> owner"
        )

    entry = frozen.pop(key)
    _save_frozen(frozen)

    return True, (
        f"Unfrozen '{filename}' {version_id}\n"
        f"  Authorized by:    {unfreeze_by} (owner)\n"
        f"  Originally frozen by: {entry['frozen_by']} "
        f"on {entry['frozen_at'][:19].replace('T', ' ')}\n"
        f"  Unfreeze reason: {reason or 'No reason provided'}\n\n"
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
        f_at         = entry["frozen_at"][:19].replace("T", " ")
        version_sigs = all_sigs.get(entry["filename"], {}).get(entry["version_id"], [])
        owners       = [s["signer"] for s in version_sigs if s["role"] == "owner"]
        owner_str    = ", ".join(owners) if owners else "none — unfreeze blocked"
        lines.append(
            f"\n  {entry['filename']} {entry['version_id']}\n"
            f"  Frozen by: {entry['frozen_by']} on {f_at}\n"
            f"  Reason:    {entry.get('reason', '—')}\n"
            f"  Hash:      {entry['file_hash'][:24]}...\n"
            f"  Owners:    {owner_str}"
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