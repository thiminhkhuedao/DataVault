import hashlib
import json
import os
import sys
import time
import threading
from datetime import datetime

HISTORY_FILE = ".datavault/history.json"


def watch(filepaths, interval=2, callback=None):
    """
    Watch one or more tracked files for unauthorized modifications.
    Polls every `interval` seconds and alerts immediately on any change.

    Run: python datavault.py watch training_data.csv
    Or:  python datavault.py watch training_data.csv labels.csv
    """
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    # Validate all files are tracked
    filenames = []
    for fp in filepaths:
        fname = os.path.basename(fp)
        if fname not in history.get("files", {}):
            return False, f"'{fname}' is not tracked. Use 'add' first."
        filenames.append((fp, fname))

    # Build initial state
    state = {}
    for fp, fname in filenames:
        versions = history["files"][fname]["versions"]
        latest   = versions[-1]
        state[fname] = {
            "filepath":     fp,
            "expected_hash": latest["hash"],
            "version_id":   latest["version_id"],
            "last_seen":    _hash_file(fp) if os.path.exists(fp) else None,
            "status":       "ok",
            "alerts":       0,
        }

    _print_header(filenames, interval)
    _print_status_table(state)

    alert_count = 0

    try:
        while True:
            time.sleep(interval)
            changed = False

            for fp, fname in filenames:
                entry     = state[fname]
                prev_hash = entry["last_seen"]

                if not os.path.exists(fp):
                    if entry["status"] != "missing":
                        entry["status"] = "missing"
                        entry["alerts"] += 1
                        alert_count += 1
                        _alert(fname, "MISSING", "File no longer exists")
                        changed = True
                    continue

                current_hash = _hash_file(fp)

                if current_hash != prev_hash and prev_hash is not None:
                    # File changed — is it authorized (matches a known version)?
                    known_hashes = {v["hash"]: v["version_id"]
                                    for v in history["files"][fname]["versions"]}

                    if current_hash in known_hashes:
                        # Changed to a known version — probably a checkout
                        vid = known_hashes[current_hash]
                        entry["status"]    = "ok"
                        entry["last_seen"] = current_hash
                        _info(fname, f"Changed to known version {vid}")
                    elif current_hash == entry["expected_hash"]:
                        entry["status"]    = "ok"
                        entry["last_seen"] = current_hash
                    else:
                        entry["status"]    = "tampered"
                        entry["last_seen"] = current_hash
                        entry["alerts"]   += 1
                        alert_count       += 1
                        _alert(
                            fname, "TAMPERED",
                            f"Unauthorized modification detected\n"
                            f"  Expected: {entry['expected_hash'][:24]}...\n"
                            f"  Current:  {current_hash[:24]}..."
                        )
                        changed = True

                elif prev_hash is None and current_hash:
                    # File reappeared
                    entry["last_seen"] = current_hash
                    if current_hash == entry["expected_hash"]:
                        entry["status"] = "ok"
                        _info(fname, "File reappeared — intact")
                    else:
                        entry["status"] = "tampered"
                        entry["alerts"] += 1
                        alert_count += 1
                        _alert(fname, "TAMPERED", "File reappeared but content differs from last commit")
                        changed = True

            if changed:
                _print_status_table(state)
            else:
                _print_heartbeat(state, interval)

    except KeyboardInterrupt:
        print(f"\n\n  Watch stopped.")
        print(f"  Total alerts: {alert_count}")
        print(f"  Monitored {len(filenames)} file(s) — press Enter to exit\n")
        return True, ""


def _hash_file(filepath):
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return None


def _print_header(filenames, interval):
    print()
    print("  DataVault Watch Mode")
    print("  " + "─" * 52)
    print(f"  Monitoring {len(filenames)} file(s) every {interval}s")
    for _, fname in filenames:
        print(f"    • {fname}")
    print(f"  Press Ctrl+C to stop")
    print("  " + "─" * 52)
    print()


def _print_status_table(state):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n  [{now}] Status:")
    for fname, entry in state.items():
        s = entry["status"]
        if s == "ok":
            icon  = "\033[92m✓\033[0m"
            label = "INTACT  "
        elif s == "tampered":
            icon  = "\033[91m✗\033[0m"
            label = "TAMPERED"
        else:
            icon  = "\033[93m?\033[0m"
            label = "MISSING "
        alerts = f"  ({entry['alerts']} alert(s))" if entry["alerts"] else ""
        print(f"    {icon} {label}  {fname}{alerts}")
    print()


def _print_heartbeat(state, interval):
    now   = datetime.now().strftime("%H:%M:%S")
    ok    = sum(1 for e in state.values() if e["status"] == "ok")
    total = len(state)
    sys.stdout.write(f"\r  [{now}] {ok}/{total} files intact — watching...")
    sys.stdout.flush()


def _alert(fname, level, message):
    now = datetime.now().strftime("%H:%M:%S")
    RED  = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    print(f"\n\n  {RED}{BOLD}[{now}] ALERT — {level}{RESET}")
    print(f"  File: {fname}")
    for line in message.split("\n"):
        print(f"  {line}")
    print(f"\n  Run: python datavault.py verify {fname}")
    print()


def _info(fname, message):
    now  = datetime.now().strftime("%H:%M:%S")
    BLUE = "\033[94m"
    RESET = "\033[0m"
    print(f"\n  {BLUE}[{now}] INFO{RESET} — {fname}: {message}")