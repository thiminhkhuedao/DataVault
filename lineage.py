import json
import os
from datetime import datetime

HISTORY_FILE = ".datavault/history.json"
LINEAGE_FILE = ".datavault/lineage.json"


def link_files(output_file, source_files, message=""):
    """
    Declare that output_file was derived from source_files.
    Example: datavault link training_data.csv raw_data.csv labels.csv
    """
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    output_name = os.path.basename(output_file)

    # Validate all files are tracked
    all_files = [output_name] + [os.path.basename(s) for s in source_files]
    for fname in all_files:
        if fname not in history.get("files", {}):
            return False, f"'{fname}' is not tracked. Track it first with 'add'."

    lineage = _load_lineage()
    created_by = os.getenv("USERNAME") or os.getenv("USER") or "unknown"

    if output_name not in lineage:
        lineage[output_name] = {"sources": [], "derived": []}

    # Add sources
    for src in source_files:
        src_name = os.path.basename(src)
        src_versions = history["files"][src_name]["versions"]
        src_latest   = src_versions[-1]

        # Avoid duplicate source entries
        existing = next((s for s in lineage[output_name]["sources"]
                        if s["filename"] == src_name), None)
        if existing:
            existing["linked_version"] = src_latest["version_id"]
            existing["linked_hash"]    = src_latest["hash"]
            existing["updated_at"]     = datetime.now().isoformat()
        else:
            lineage[output_name]["sources"].append({
                "filename":       src_name,
                "linked_version": src_latest["version_id"],
                "linked_hash":    src_latest["hash"],
                "linked_at":      datetime.now().isoformat(),
                "linked_by":      created_by,
            })

        # Register reverse link in source
        if src_name not in lineage:
            lineage[src_name] = {"sources": [], "derived": []}
        if output_name not in lineage[src_name]["derived"]:
            lineage[src_name]["derived"].append(output_name)

    if message:
        lineage[output_name]["message"] = message
    lineage[output_name]["updated_at"] = datetime.now().isoformat()

    _save_lineage(lineage)

    src_names = ", ".join(os.path.basename(s) for s in source_files)
    return True, (
        f"Lineage recorded: {output_name}\n"
        f"  Derived from: {src_names}\n"
        f"  By: {created_by}"
    )


def show_lineage(filepath, depth=0, visited=None, direction="both"):
    """
    Display the full lineage tree for a file —
    both upstream (where it came from) and downstream (what was derived from it).
    """
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    filename = os.path.basename(filepath)
    lineage  = _load_lineage()

    if filename not in lineage and filename not in _all_tracked_files():
        return False, f"'{filename}' is not tracked."

    lines = [f"\nLineage: '{filename}'\n" + "─" * 55]

    # Upstream tree (sources)
    lines.append("\n  UPSTREAM (where this data came from):")
    upstream = _build_upstream(filename, lineage, visited=set())
    if upstream:
        for line in upstream:
            lines.append(line)
    else:
        lines.append("    No declared sources — this is a root dataset")

    # Downstream tree (derived files)
    lines.append("\n  DOWNSTREAM (what was derived from this data):")
    downstream = _build_downstream(filename, lineage, visited=set())
    if downstream:
        for line in downstream:
            lines.append(line)
    else:
        lines.append("    No derived files declared")

    # Source integrity check
    if filename in lineage and lineage[filename].get("sources"):
        lines.append("\n  SOURCE INTEGRITY:")
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

        all_ok = True
        for src in lineage[filename]["sources"]:
            src_name = src["filename"]
            if src_name in history.get("files", {}):
                src_versions = history["files"][src_name]["versions"]
                current_hash = src_versions[-1]["hash"]
                linked_hash  = src["linked_hash"]
                if current_hash == linked_hash:
                    lines.append(f"    ✓ {src_name} — unchanged since link")
                else:
                    all_ok = False
                    lines.append(f"    ✗ {src_name} — MODIFIED since link")
                    lines.append(f"      linked hash:  {linked_hash[:24]}...")
                    lines.append(f"      current hash: {current_hash[:24]}...")
            else:
                lines.append(f"    ? {src_name} — no longer tracked")

        if all_ok:
            lines.append("\n  ✓ All source files unchanged since lineage was declared")
        else:
            lines.append("\n  ✗ Some source files have changed — consider re-running your pipeline")

    return True, "\n".join(lines)


def list_lineage():
    """List all declared lineage relationships"""
    lineage = _load_lineage()

    if not lineage:
        return True, "No lineage declared yet. Use 'datavault link' to declare dependencies."

    lines = ["\nAll declared lineage:\n" + "─" * 55]

    for filename, data in lineage.items():
        sources = data.get("sources", [])
        derived = data.get("derived", [])
        if sources or derived:
            lines.append(f"\n  {filename}")
            if sources:
                src_names = ", ".join(s["filename"] for s in sources)
                lines.append(f"    ← derived from: {src_names}")
            if derived:
                lines.append(f"    → used in:      {', '.join(derived)}")

    return True, "\n".join(lines)


def _build_upstream(filename, lineage, visited, indent=4):
    if filename in visited:
        return [" " * indent + f"↑ {filename} (already shown)"]
    visited.add(filename)

    lines = []
    data  = lineage.get(filename, {})
    sources = data.get("sources", [])

    for src in sources:
        src_name = src["filename"]
        at       = src["linked_at"][:10]
        lines.append(" " * indent + f"↑ {src_name}  (linked {at}, version {src['linked_version']})")
        # Recurse
        parent_lines = _build_upstream(src_name, lineage, visited, indent + 4)
        lines.extend(parent_lines)

    return lines


def _build_downstream(filename, lineage, visited, indent=4):
    if filename in visited:
        return [" " * indent + f"↓ {filename} (already shown)"]
    visited.add(filename)

    lines   = []
    data    = lineage.get(filename, {})
    derived = data.get("derived", [])

    for child in derived:
        lines.append(" " * indent + f"↓ {child}")
        child_lines = _build_downstream(child, lineage, visited, indent + 4)
        lines.extend(child_lines)

    return lines


def _all_tracked_files():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
    return set(history.get("files", {}).keys())


def _load_lineage():
    if os.path.exists(LINEAGE_FILE):
        with open(LINEAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_lineage(data):
    os.makedirs(os.path.dirname(LINEAGE_FILE), exist_ok=True)
    with open(LINEAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)