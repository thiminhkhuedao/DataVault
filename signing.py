# ============================================================
# signing.py — multi-user approval and signing system
#
# Usage:
#   python datavault.py sign training_data.csv v2 "nguye" reviewer
#   python datavault.py sign training_data.csv v2 "alice" approver
#   python datavault.py signatures training_data.csv v2
#   python datavault.py approve training_data.csv v2
# ============================================================

import hashlib
import json
import os
from datetime import datetime

HISTORY_FILE  = ".datavault/history.json"
SIGNING_FILE  = ".datavault/signatures.json"

ROLES = ["reviewer", "approver", "owner", "witness"]

# ── Signing ───────────────────────────────────────────────────

def sign_version(filepath, version_id, signer_name, role="reviewer"):
   
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    if role not in ROLES:
        return False, f"Invalid role '{role}'. Choose from: {', '.join(ROLES)}"

    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)

    filename = os.path.basename(filepath)
    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions = history["files"][filename]["versions"]
    target   = next((v for v in versions if v["version_id"] == version_id), None)

    if not target:
        available = ", ".join(v["version_id"] for v in versions)
        return False, f"Version '{version_id}' not found. Available: {available}"

    # Create signature hash — binds signer to this exact version
    # If the file content changes, this signature becomes invalid
    signed_at       = datetime.now().isoformat()
    signature_input = f"{signer_name}|{role}|{target['hash']}|{version_id}|{signed_at}"
    signature_hash  = hashlib.sha256(signature_input.encode()).hexdigest()[:32]

    # Load existing signatures
    sigs = _load_signatures()
    if filename not in sigs:
        sigs[filename] = {}
    if version_id not in sigs[filename]:
        sigs[filename][version_id] = []

    # Check if this person already signed this version in this role
    already_signed = any(
        s["signer"] == signer_name and s["role"] == role
        for s in sigs[filename][version_id]
    )
    if already_signed:
        return False, f"'{signer_name}' has already signed {version_id} as {role}."

    # Add signature
    signature = {
        "signer":         signer_name,
        "role":           role,
        "signed_at":      signed_at,
        "file_hash":      target["hash"],     # what exactly was signed
        "signature_hash": signature_hash,     # proof of who+when+what
        "version_id":     version_id
    }
    sigs[filename][version_id].append(signature)
    _save_signatures(sigs)

    return True, (
        f"Signed '{filename}' {version_id}\n"
        f"  Signer:    {signer_name} ({role})\n"
        f"  File hash: {target['hash'][:24]}…\n"
        f"  Sig hash:  {signature_hash[:24]}…\n"
        f"  At:        {signed_at[:19].replace('T',' ')}\n"
        f"\n  This signature is cryptographically tied to version {version_id}.\n"
        f"  If the file content changes, this signature becomes invalid."
    )

# ── Verifying signatures ──────────────────────────────────────

def verify_signatures(filepath, version_id):
   
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)

    filename = os.path.basename(filepath)
    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions = history["files"][filename]["versions"]
    target   = next((v for v in versions if v["version_id"] == version_id), None)
    if not target:
        return False, f"Version '{version_id}' not found."

    sigs = _load_signatures()
    version_sigs = sigs.get(filename, {}).get(version_id, [])

    if not version_sigs:
        return True, f"No signatures for {version_id} yet."

    lines     = [f"\nSignatures for '{filename}' {version_id}:\n" + "─"*55]
    all_valid = True

    for sig in version_sigs:
        # Recompute signature hash to verify it hasn't been tampered with
        expected_input = f"{sig['signer']}|{sig['role']}|{sig['file_hash']}|{sig['version_id']}|{sig['signed_at']}"
        expected_hash  = hashlib.sha256(expected_input.encode()).hexdigest()[:32]

        sig_valid  = (expected_hash == sig["signature_hash"])
        hash_valid = (sig["file_hash"] == target["hash"])

        if sig_valid and hash_valid:
            ts = sig["signed_at"][:19].replace("T", " ")
            lines.append(
                f"\n  ✓ {sig['signer']} ({sig['role']})\n"
                f"    Signed: {ts}\n"
                f"    Sig:    {sig['signature_hash'][:24]}…"
            )
        elif not hash_valid:
            all_valid = False
            lines.append(
                f"\n  ✗ {sig['signer']} ({sig['role']}) — INVALID\n"
                f"    File was modified after this signature was created.\n"
                f"    Signed hash:  {sig['file_hash'][:24]}…\n"
                f"    Current hash: {target['hash'][:24]}…"
            )
        else:
            all_valid = False
            lines.append(
                f"\n  ✗ {sig['signer']} ({sig['role']}) — SIGNATURE TAMPERED\n"
                f"    The signature record itself was modified."
            )

    lines.append(f"\n{'─'*55}")
    if all_valid:
        lines.append(f"  ✓ All {len(version_sigs)} signature(s) valid")
    else:
        lines.append(f"  ✗ Some signatures are invalid — see above")

    return all_valid, "\n".join(lines)

# ── Approval status ───────────────────────────────────────────

def approval_status(filepath, version_id, require_approver=True, require_reviewer=True):
    
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    filename    = os.path.basename(filepath)
    sigs        = _load_signatures()
    version_sigs = sigs.get(filename, {}).get(version_id, [])

    has_reviewer = any(s["role"] == "reviewer"  for s in version_sigs)
    has_approver = any(s["role"] == "approver"  for s in version_sigs)
    has_owner    = any(s["role"] == "owner"     for s in version_sigs)

    missing = []
    if require_reviewer and not has_reviewer:
        missing.append("reviewer")
    if require_approver and not has_approver:
        missing.append("approver")

    approved = len(missing) == 0 and len(version_sigs) > 0

    lines = [f"\nApproval status: '{filename}' {version_id}\n" + "─"*55]
    lines.append(f"\n  Reviewer:  {'✓' if has_reviewer else '✗ missing'}")
    lines.append(f"  Approver:  {'✓' if has_approver else '✗ missing'}")
    lines.append(f"  Owner:     {'✓' if has_owner else '— (optional)'}")
    lines.append(f"\n  Total signatures: {len(version_sigs)}")

    if approved:
        lines.append(f"\n  ✓ APPROVED — ready for use in AI training")
    else:
        lines.append(f"\n  ✗ NOT APPROVED — missing: {', '.join(missing)}")
        lines.append(f"  Run: python datavault.py sign {filepath} {version_id} <name> <role>")

    return approved, "\n".join(lines)

# ── List all signatures across all versions ───────────────────

def list_all_signatures(filepath):
    """Show all signatures across all versions of a file"""
    filename    = os.path.basename(filepath)
    sigs        = _load_signatures()
    file_sigs   = sigs.get(filename, {})

    if not file_sigs:
        return True, f"No signatures found for '{filename}'."

    lines = [f"\nAll signatures for '{filename}':\n" + "─"*55]

    for version_id, version_sigs in file_sigs.items():
        lines.append(f"\n  {version_id} ({len(version_sigs)} signature(s)):")
        for sig in version_sigs:
            ts = sig["signed_at"][:19].replace("T", " ")
            lines.append(f"    • {sig['signer']} ({sig['role']}) — {ts}")

    return True, "\n".join(lines)

# ── Helpers ───────────────────────────────────────────────────

def _load_signatures():
    if os.path.exists(SIGNING_FILE):
        with open(SIGNING_FILE, "r") as f:
            return json.load(f)
    return {}

def _save_signatures(data):
    os.makedirs(os.path.dirname(SIGNING_FILE), exist_ok=True)
    with open(SIGNING_FILE, "w") as f:
        json.dump(data, f, indent=2)