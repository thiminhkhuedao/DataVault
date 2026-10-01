import csv
import hashlib
import json
import os

ROWLOG_DIR   = ".datavault/rowlogs"
HISTORY_FILE = ".datavault/history.json"


def hash_row(row_dict):
    row_str = json.dumps(row_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(row_str.encode()).hexdigest()[:16]


def parse_csv_rows(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            reader  = csv.DictReader(f)
            headers = reader.fieldnames or []
            rows    = [dict(row) for row in reader]
        return headers, rows
    except Exception:
        return [], []


def build_row_snapshot(filepath):
    headers, rows = parse_csv_rows(filepath)
    if not rows:
        return {}, headers
    snapshot = {}
    for i, row in enumerate(rows):
        row_hash = hash_row(row)
        snapshot[row_hash] = {"position": i, "data": row, "hash": row_hash}
    return snapshot, headers


def save_row_snapshot(filename, version_id, snapshot, headers):
    os.makedirs(ROWLOG_DIR, exist_ok=True)
    safe_name = filename.replace("/", "_").replace("\\", "_")
    path      = os.path.join(ROWLOG_DIR, f"{safe_name}__{version_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"headers": headers, "rows": snapshot}, f, indent=2)


def load_row_snapshot(filename, version_id):
    safe_name = filename.replace("/", "_").replace("\\", "_")
    path      = os.path.join(ROWLOG_DIR, f"{safe_name}__{version_id}.json")
    if not os.path.exists(path):
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("rows", {}), data.get("headers", [])


def snapshot_on_commit(filepath, version_id):
    if not filepath.lower().endswith(".csv"):
        return False
    filename          = os.path.basename(filepath)
    snapshot, headers = build_row_snapshot(filepath)
    if snapshot:
        save_row_snapshot(filename, version_id, snapshot, headers)
        return True
    return False


def row_diff(filepath, version_a, version_b):
    filename        = os.path.basename(filepath)
    snap_a, headers = load_row_snapshot(filename, version_a)
    snap_b, _       = load_row_snapshot(filename, version_b)

    if snap_a is None:
        return False, f"No row snapshot for {version_a}. Re-commit to generate one."
    if snap_b is None:
        return False, f"No row snapshot for {version_b}. Re-commit to generate one."

    hashes_a = set(snap_a.keys())
    hashes_b = set(snap_b.keys())
    added    = hashes_b - hashes_a
    deleted  = hashes_a - hashes_b
    moved    = [(h, snap_a[h]["position"], snap_b[h]["position"])
                for h in hashes_a & hashes_b
                if snap_a[h]["position"] != snap_b[h]["position"]]

    lines = [
        f"\nRow-level diff: '{filename}'  {version_a} → {version_b}",
        "─" * 55,
        f"  Rows added:   {len(added)}",
        f"  Rows deleted: {len(deleted)}",
        f"  Rows moved:   {len(moved)}",
        f"  Unchanged:    {len(hashes_a & hashes_b) - len(moved)}",
        ""
    ]
    if added:
        lines.append("  ADDED rows:")
        for h in list(added)[:10]:
            lines.append(f"    + {dict(list(snap_b[h]['data'].items())[:4])}")
        if len(added) > 10:
            lines.append(f"    ... and {len(added)-10} more")
    if deleted:
        lines.append("\n  DELETED rows:")
        for h in list(deleted)[:10]:
            lines.append(f"    - {dict(list(snap_a[h]['data'].items())[:4])}")
        if len(deleted) > 10:
            lines.append(f"    ... and {len(deleted)-10} more")
    if moved:
        lines.append("\n  MOVED rows:")
        for h, pos_a, pos_b in moved[:5]:
            lines.append(f"    ~ row {pos_a+1} → row {pos_b+1}: {dict(list(snap_a[h]['data'].items())[:2])}")

    return True, "\n".join(lines)


def row_history(filepath, row_identifier_col, row_identifier_val):
    filename = os.path.basename(filepath)
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)

    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions = history["files"][filename]["versions"]
    timeline = []

    for v in versions:
        snapshot, _ = load_row_snapshot(filename, v["version_id"])
        if snapshot is None:
            continue
        found = next(
            (row_data for row_data in snapshot.values()
             if row_data["data"].get(row_identifier_col) == str(row_identifier_val)),
            None
        )
        timeline.append({"version_id": v["version_id"], "timestamp": v["timestamp"], "message": v["message"], "row": found})

    if not any(t["row"] for t in timeline):
        return False, f"No row found where {row_identifier_col}={row_identifier_val}\nCheck your CSV headers."

    lines    = [f"\nRow history: {filename} where {row_identifier_col}={row_identifier_val}", "─" * 55]
    prev_row = None

    for entry in timeline:
        ts  = entry["timestamp"][:19].replace("T", " ")
        row = entry["row"]
        lines.append(f"\n  {entry['version_id']}  |  {ts}")
        if row is None:
            lines.append(f"  ✗ Row not present in this version")
        else:
            lines.append(f"  Message: {entry['message']}")
            if prev_row and prev_row != row["data"]:
                changed = {k: f"{prev_row.get(k,'—')} → v" for k, v in row["data"].items() if row["data"].get(k) != prev_row.get(k)}
                lines.append(f"  Changes: {changed}" if changed else f"  Position moved: row {row['position']+1}")
            elif prev_row is None:
                lines.append(f"  First appearance: {row['data']}")
            prev_row = row["data"]

    return True, "\n".join(lines)


def row_stats(filepath):
    filename = os.path.basename(filepath)
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)

    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions      = history["files"][filename]["versions"]
    lines         = [f"\nRow statistics: '{filename}'\n" + "─"*50]
    prev_snapshot = None
    total_added   = 0
    total_deleted = 0

    for v in versions:
        snapshot, _ = load_row_snapshot(filename, v["version_id"])
        if snapshot is None:
            lines.append(f"\n  {v['version_id']}: no row snapshot available")
            continue
        ts = v["timestamp"][:19].replace("T", " ")
        if prev_snapshot is not None:
            added         = len(set(snapshot.keys()) - set(prev_snapshot.keys()))
            deleted       = len(set(prev_snapshot.keys()) - set(snapshot.keys()))
            total_added   += added
            total_deleted += deleted
            change_str    = f"+{added} added, -{deleted} deleted"
        else:
            change_str = "initial snapshot"
        lines.append(f"\n  {v['version_id']}  |  {ts}")
        lines.append(f"  {len(snapshot)} rows total  |  {change_str}")
        lines.append(f"  \"{v['message']}\"")
        prev_snapshot = snapshot

    lines.append(f"\n{'─'*50}")
    lines.append(f"  Total rows added across all versions:   {total_added}")
    lines.append(f"  Total rows deleted across all versions: {total_deleted}")
    return True, "\n".join(lines)