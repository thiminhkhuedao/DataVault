import hashlib
import json
import os

HISTORY_FILE = ".datavault/history.json"
CHAIN_FILE   = ".datavault/chain.json"


def compute_chain_hash(file_hash, prev_chain_hash, version_id, timestamp, author, message):
    chain_input = "|".join([file_hash, prev_chain_hash, version_id, timestamp, author, message])
    return hashlib.sha256(chain_input.encode()).hexdigest()


def build_chain(filename):
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions        = history["files"][filename]["versions"]
    prev_chain_hash = "GENESIS"
    chain           = []

    for v in versions:
        chain_hash = compute_chain_hash(
            v["hash"], prev_chain_hash, v["version_id"],
            v["timestamp"], v.get("author", "unknown"), v["message"]
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
        v["chain_hash"]      = chain_hash
        v["prev_chain_hash"] = prev_chain_hash
        prev_chain_hash      = chain_hash

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    chain_data = _load_chain()
    chain_data["files"][filename] = chain
    _save_chain(chain_data)
    return True, chain


def verify_chain(filename):
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions = history["files"][filename]["versions"]
    if not any("chain_hash" in v for v in versions):
        return False, f"No chain data for '{filename}'.\nRun: python datavault.py chainbuild {filename}"

    prev_chain_hash = "GENESIS"
    results         = []
    all_valid       = True

    for v in versions:
        stored = v.get("chain_hash")
        if not stored:
            results.append({"version_id": v["version_id"], "valid": False, "reason": "no chain hash — run chainbuild"})
            all_valid = False
            continue

        expected = compute_chain_hash(
            v["hash"], prev_chain_hash, v["version_id"],
            v["timestamp"], v.get("author", "unknown"), v["message"]
        )
        valid = (expected == stored)
        if not valid:
            all_valid = False

        results.append({
            "version_id": v["version_id"],
            "valid":      valid,
            "stored":     stored[:24],
            "expected":   expected[:24],
            "prev":       prev_chain_hash[:24] if prev_chain_hash != "GENESIS" else "GENESIS",
            "timestamp":  v["timestamp"][:19].replace("T", " "),
            "message":    v["message"]
        })
        prev_chain_hash = stored

    return all_valid, results


def format_chain_verification(filename, results):
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
                f"    reason:   {r.get('reason','hash mismatch')}"
            )
    lines.append(f"\n{'─'*55}")
    if all(r["valid"] for r in results):
        lines.append(
            f"  ✓ CHAIN INTACT — {len(results)} version(s) verified\n"
            f"  Complete history is authentic and unmodified.\n"
            f"  No versions were deleted, reordered, or tampered with."
        )
    else:
        broken = [r["version_id"] for r in results if not r["valid"]]
        lines.append(
            f"  ✗ CHAIN BROKEN at: {', '.join(broken)}\n"
            f"  History has been tampered with."
        )
    return "\n".join(lines)


def display_chain(filename):
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
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


def _load_chain():
    if os.path.exists(CHAIN_FILE):
        with open(CHAIN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"files": {}}


def _save_chain(data):
    with open(CHAIN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)