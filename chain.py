# ============================================================
# chain.py — cryptographic hash chain for DataVault
#
# Usage:
#   python datavault.py chain training_data.csv    → verify the full chain
#   python datavault.py chainshow training_data.csv → display the chain visually
# ============================================================

import hashlib
import json
import os
from datetime import datetime

HISTORY_FILE = ".datavault/history.json"
CHAIN_FILE   = ".datavault/chain.json"

# ── Building the chain ────────────────────────────────────────

def compute_chain_hash(file_hash, prev_chain_hash, version_id, timestamp, author, message):
    
    chain_input = "|".join([
        file_hash,
        prev_chain_hash,
        version_id,
        timestamp,
        author,
        message
    ])
    return hashlib.sha256(chain_input.encode()).hexdigest()

def build_chain(filename):
    
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)

    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions        = history["files"][filename]["versions"]
    prev_chain_hash = "GENESIS"
    chain           = []

    for v in versions:
        chain_hash = compute_chain_hash(
            file_hash       = v["hash"],
            prev_chain_hash = prev_chain_hash,
            version_id      = v["version_id"],
            timestamp       = v["timestamp"],
            author          = v.get("author", "unknown"),
            message         = v["message"]
        )

        chain.append({
            "version_id":      v["version_id"],
            "file_hash":       v["hash"],
            "prev_chain_hash": prev_chain_hash,
            "chain_hash":      chain_hash,
            "timestamp":       v["timestamp"],
            "author":          v.get("author", "unknown"),
            "message":         v["message"]
        })

        # Store chain hash back into the version record
        v["chain_hash"]      = chain_hash
        v["prev_chain_hash"] = prev_chain_hash

        prev_chain_hash = chain_hash

    # Save updated history with chain hashes embedded
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    # Also save chain separately for easy inspection
    chain_data = _load_chain()
    chain_data["files"][filename] = chain
    _save_chain(chain_data)

    return True, chain

# ── Verifying the chain ───────────────────────────────────────

def verify_chain(filename):
    
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)

    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions = history["files"][filename]["versions"]

    if not any("chain_hash" in v for v in versions):
        return False, (
            f"No chain data for '{filename}'.\n"
            f"Run: python datavault.py chainbuild {filename}"
        )

    prev_chain_hash = "GENESIS"
    results         = []
    all_valid       = True

    for v in versions:
        stored_chain_hash = v.get("chain_hash")

        if not stored_chain_hash:
            results.append({
                "version_id": v["version_id"],
                "valid":      False,
                "reason":     "no chain hash stored — run chainbuild"
            })
            all_valid = False
            continue

        # Recompute what the chain hash SHOULD be
        expected_chain_hash = compute_chain_hash(
            file_hash       = v["hash"],
            prev_chain_hash = prev_chain_hash,
            version_id      = v["version_id"],
            timestamp       = v["timestamp"],
            author          = v.get("author", "unknown"),
            message         = v["message"]
        )

        valid = (expected_chain_hash == stored_chain_hash)

        results.append({
            "version_id":    v["version_id"],
            "valid":         valid,
            "stored":        stored_chain_hash[:24],
            "expected":      expected_chain_hash[:24],
            "prev":          prev_chain_hash[:24] if prev_chain_hash != "GENESIS" else "GENESIS",
            "timestamp":     v["timestamp"][:19].replace("T", " "),
            "message":       v["message"]
        })

        if not valid:
            all_valid = False
            # Don't break — continue checking so we can show exactly where chain broke

        prev_chain_hash = stored_chain_hash  # use stored, not expected

    return all_valid, results

def format_chain_verification(filename, results):
    """Format chain verification results for display"""
    lines = [f"\nChain verification: '{filename}'\n" + "─"*55]

    for r in results:
        if r["valid"]:
            lines.append(
                f"\n  ✓ {r['version_id']}  |  {r.get('timestamp','')}\n"
                f"    chain: {r.get('stored','?')}…\n"
                f"    prev:  {r.get('prev','?')}…\n"
                f"    \"{r.get('message','')}\""
            )
        else:
            lines.append(
                f"\n  ✗ {r['version_id']}  CHAIN BROKEN\n"
                f"    stored:   {r.get('stored','?')}…\n"
                f"    expected: {r.get('expected','?')}…\n"
                f"    reason:   {r.get('reason','hash mismatch — version was tampered with')}"
            )

    all_valid = all(r["valid"] for r in results)

    lines.append(f"\n{'─'*55}")
    if all_valid:
        lines.append(
            f"  ✓ CHAIN INTACT — {len(results)} version(s) verified\n"
            f"  Complete history is authentic and unmodified.\n"
            f"  No versions were deleted, reordered, or tampered with."
        )
    else:
        broken = [r["version_id"] for r in results if not r["valid"]]
        lines.append(
            f"  ✗ CHAIN BROKEN at: {', '.join(broken)}\n"
            f"  History has been tampered with.\n"
            f"  Some versions were modified, deleted, or reordered."
        )

    return "\n".join(lines)

# ── Visual chain display ──────────────────────────────────────

def display_chain(filename):
   
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)

    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions = history["files"][filename]["versions"]
    lines    = [f"\nHash chain: '{filename}'\n" + "─"*55]
    lines.append("  (Each block's hash includes the previous block's hash)")
    lines.append("  (Changing any block invalidates all blocks after it)\n")

    for i, v in enumerate(versions):
        chain_hash = v.get("chain_hash", "not computed")[:20]
        file_hash  = v["hash"][:20]
        prev_hash  = v.get("prev_chain_hash", "GENESIS")
        if prev_hash != "GENESIS":
            prev_hash = prev_hash[:20]

        # Draw the block
        lines.append(f"  ┌─────────────────────────────────────┐")
        lines.append(f"  │  {v['version_id']}  {v['timestamp'][:10]}           │")
        lines.append(f"  │  file hash:  {file_hash}…  │")
        lines.append(f"  │  prev hash:  {prev_hash}…  │")
        lines.append(f"  │  chain hash: {chain_hash}…  │")
        lines.append(f"  │  \"{v['message'][:30]}\"")
        lines.append(f"  └──────────────────┬──────────────────┘")
        if i < len(versions) - 1:
            lines.append(f"                     │")
            lines.append(f"                     ▼")

    return True, "\n".join(lines)

# ── Helpers ───────────────────────────────────────────────────

def _load_chain():
    if os.path.exists(CHAIN_FILE):
        with open(CHAIN_FILE, "r") as f:
            return json.load(f)
    return {"files": {}}

def _save_chain(data):
    with open(CHAIN_FILE, "w") as f:
        json.dump(data, f, indent=2)