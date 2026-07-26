# ============================================================
# vault_core.py — the engine of DataVault
#
# You never run this file directly.
# datavault.py (the main tool) calls functions from here.
# ============================================================

import hashlib
import json
import os
import shutil
from datetime import datetime


# ── Where DataVault stores everything ───────────────────────
# When you run "datavault init", it creates a hidden folder
# called .datavault in your project directory.
# All versions, history, and metadata live inside it.

VAULT_DIR      = ".datavault"          
VERSIONS_DIR   = ".datavault/versions" 
HISTORY_FILE   = ".datavault/history.json" 
META_FILE      = ".datavault/meta.json"   


# ── Hashing ─────────────────────────────────────────────────

def hash_file(filepath):
 
    sha256 = hashlib.sha256()
    
    try:
        with open(filepath, "rb") as f:  # "rb" = read as raw bytes
            # Read in 64KB chunks — handles large files without
            # loading the whole thing into memory
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()  # returns the 64-character string
    except FileNotFoundError:
        return None

def hash_string(text):
    """Hash a string directly (used for version IDs)"""
    return hashlib.sha256(text.encode()).hexdigest()[:12]


# ── Project initialization ───────────────────────────────────

def init_project(project_name):
    """
    Create the .datavault folder structure.
    Called when user runs: datavault init <name>
    """
    if os.path.exists(VAULT_DIR):
        return False, "Project already initialized."
    
    # Create folder structure
    os.makedirs(VERSIONS_DIR)
    
    # Create project metadata file
    meta = {
        "project_name": project_name,
        "created_at":   datetime.now().isoformat(),
        "created_by":   os.getenv("USERNAME") or os.getenv("USER") or "unknown"
    }
    _write_json(META_FILE, meta)
    
    # Create empty history file
    _write_json(HISTORY_FILE, {"files": {}})
    
    return True, f"Initialized DataVault project '{project_name}'"


# ── Adding and committing files ──────────────────────────────

def add_file(filepath, message):

    _check_initialized()
    
    if not os.path.exists(filepath):
        return False, f"File not found: {filepath}"
    
    history = _read_history()
    filename = os.path.basename(filepath)
    
    if filename in history["files"]:
        return False, f"'{filename}' is already tracked. Use 'commit' to log changes."
    
    # Get file fingerprint
    file_hash = hash_file(filepath)
    
    # Generate version ID (short hash of filename + timestamp)
    version_id = "v1"
    
    # Copy file into vault storage
    version_path = _version_path(filename, version_id)
    shutil.copy2(filepath, version_path)
    
    # Record in history
    history["files"][filename] = {
        "versions": [
            {
                "version_id":  version_id,
                "hash":        file_hash,
                "message":     message,
                "timestamp":   datetime.now().isoformat(),
                "author":      _get_author(),
                "size_bytes":  os.path.getsize(filepath)
            }
        ]
    }
    _write_history(history)
    
    return True, (f"Now tracking '{filename}'\n"
                  f"  Version:  {version_id}\n"
                  f"  Hash:     {file_hash[:16]}...\n"
                  f"  Message:  {message}")


def commit_file(filepath, message):
  
    _check_initialized()
    
    if not os.path.exists(filepath):
        return False, f"File not found: {filepath}"
    
    history = _read_history()
    filename = os.path.basename(filepath)
    
    if filename not in history["files"]:
        return False, f"'{filename}' is not tracked yet. Use 'add' first."
    
    versions     = history["files"][filename]["versions"]
    last_version = versions[-1]
    current_hash = hash_file(filepath)
    
    # Check if file actually changed
    if current_hash == last_version["hash"]:
        return False, f"No changes detected in '{filename}'. File is identical to last version."
    
    # New version number
    version_num = len(versions) + 1
    version_id  = f"v{version_num}"
    
    # Save copy to vault
    version_path = _version_path(filename, version_id)
    shutil.copy2(filepath, version_path)
    
    # Add to history
    new_version = {
        "version_id":  version_id,
        "hash":        current_hash,
        "message":     message,
        "timestamp":   datetime.now().isoformat(),
        "author":      _get_author(),
        "size_bytes":  os.path.getsize(filepath),
        "prev_hash":   last_version["hash"]  # link to previous version
    }
    versions.append(new_version)
    _write_history(history)
    
    return True, (f"Committed new version of '{filename}'\n"
                  f"  Version:  {version_id}\n"
                  f"  Hash:     {current_hash[:16]}...\n"
                  f"  Previous: {last_version['hash'][:16]}...\n"
                  f"  Message:  {message}")


# ── Reading history ──────────────────────────────────────────

def get_log(filepath):
    
    _check_initialized()
    history  = _read_history()
    filename = os.path.basename(filepath)
    
    if filename not in history["files"]:
        return False, f"'{filename}' is not tracked."
    
    versions = history["files"][filename]["versions"]
    lines    = [f"\nHistory of '{filename}' ({len(versions)} version(s))\n" + "─"*50]
    
    # Show newest first
    for v in reversed(versions):
        timestamp = v["timestamp"][:19].replace("T", " ")
        lines.append(
            f"\n  {v['version_id']}  |  {timestamp}\n"
            f"  Author:  {v['author']}\n"
            f"  Message: {v['message']}\n"
            f"  Hash:    {v['hash'][:32]}...\n"
            f"  Size:    {_format_size(v['size_bytes'])}"
        )
    
    return True, "\n".join(lines)


def list_files():
   
    _check_initialized()
    history = _read_history()
    
    if not history["files"]:
        return True, "No files tracked yet. Use 'add' to start tracking a file."
    
    lines = ["\nTracked files:\n" + "─"*50]
    
    for filename, data in history["files"].items():
        versions     = data["versions"]
        latest       = versions[-1]
        version_count = len(versions)
        timestamp    = latest["timestamp"][:19].replace("T", " ")
        
        # Check if current file matches latest stored version
        current_path = filename
        if os.path.exists(current_path):
            current_hash = hash_file(current_path)
            status = "✓ up to date" if current_hash == latest["hash"] else "⚠ modified — run commit"
        else:
            status = "✗ file missing"
        
        lines.append(
            f"\n  {filename}\n"
            f"  {version_count} version(s) | latest: {latest['version_id']} | {timestamp}\n"
            f"  Status: {status}"
        )
    
    return True, "\n".join(lines)


# ── Verification ─────────────────────────────────────────────

def verify_file(filepath):

    _check_initialized()
    history  = _read_history()
    filename = os.path.basename(filepath)
    
    if filename not in history["files"]:
        return False, f"'{filename}' is not tracked."
    
    if not os.path.exists(filepath):
        return False, f"File not found: {filepath}"
    
    latest       = history["files"][filename]["versions"][-1]
    current_hash = hash_file(filepath)
    stored_hash  = latest["hash"]
    
    if current_hash == stored_hash:
        return True, (
            f"\n✓ VERIFIED — '{filename}' is authentic\n"
            f"  Current hash:  {current_hash[:32]}...\n"
            f"  Stored hash:   {stored_hash[:32]}...\n"
            f"  Last commit:   {latest['timestamp'][:19].replace('T',' ')}\n"
            f"  By:            {latest['author']}\n"
            f"  Message:       {latest['message']}"
        )
    else:
        return False, (
            f"\n✗ TAMPERED — '{filename}' has been modified outside DataVault\n"
            f"  Current hash:  {current_hash[:32]}...\n"
            f"  Expected hash: {stored_hash[:32]}...\n"
            f"\n  This file cannot be trusted. Use 'checkout' to restore\n"
            f"  the last verified version, or 'commit' to log the change."
        )


# ── Checkout (restore old version) ──────────────────────────

def checkout_version(filepath, version_id):
   
    _check_initialized()
    history  = _read_history()
    filename = os.path.basename(filepath)
    
    if filename not in history["files"]:
        return False, f"'{filename}' is not tracked."
    
    versions   = history["files"][filename]["versions"]
    target     = next((v for v in versions if v["version_id"] == version_id), None)
    
    if not target:
        available = ", ".join(v["version_id"] for v in versions)
        return False, f"Version '{version_id}' not found. Available: {available}"
    
    # Copy stored version back to working directory
    stored_path = _version_path(filename, version_id)
    shutil.copy2(stored_path, filepath)
    
    return True, (
        f"Restored '{filename}' to {version_id}\n"
        f"  From:    {target['timestamp'][:19].replace('T',' ')}\n"
        f"  Message: {target['message']}\n"
        f"  Hash:    {target['hash'][:32]}..."
    )


# ── Diff (what changed between versions) ────────────────────

def diff_versions(filepath, version_a, version_b):
    
    _check_initialized()
    history  = _read_history()
    filename = os.path.basename(filepath)
    
    if filename not in history["files"]:
        return False, f"'{filename}' is not tracked."
    
    versions = history["files"][filename]["versions"]
    va       = next((v for v in versions if v["version_id"] == version_a), None)
    vb       = next((v for v in versions if v["version_id"] == version_b), None)
    
    if not va:
        return False, f"Version '{version_a}' not found."
    if not vb:
        return False, f"Version '{version_b}' not found."
    
    path_a = _version_path(filename, version_a)
    path_b = _version_path(filename, version_b)
    
    # Read both versions
    try:
        with open(path_a, "r", encoding="utf-8") as f:
            lines_a = f.readlines()
        with open(path_b, "r", encoding="utf-8") as f:
            lines_b = f.readlines()
    except:
        return False, "Could not read file versions (only text/CSV files supported for diff)"
    
    # Simple line-by-line diff
    import difflib
    diff = list(difflib.unified_diff(
        lines_a, lines_b,
        fromfile=f"{filename} ({version_a})",
        tofile=f"{filename} ({version_b})",
        lineterm=""
    ))
    
    if not diff:
        return True, f"No differences between {version_a} and {version_b}"
    
    lines = [f"\nDiff: {filename}  {version_a} → {version_b}\n" + "─"*50]
    for line in diff[:100]:  # limit to 100 lines
        if line.startswith("+"):
            lines.append(f"  + {line[1:]}")
        elif line.startswith("-"):
            lines.append(f"  - {line[1:]}")
        elif line.startswith("@@"):
            lines.append(f"\n  {line}")
    
    if len(diff) > 100:
        lines.append(f"\n  ... and {len(diff)-100} more lines")
    
    return True, "\n".join(lines)


# ── PDF Export ──────────────────────────────────────────────

def export_pdf(output_path="datavault_report.pdf"):
   
    _check_initialized()
    history = _read_history()
    meta    = _read_json(META_FILE)

    if not history["files"]:
        return False, "No tracked files to export."

    # Build the PDF using only standard library (no reportlab needed)
    # We generate a clean HTML file and convert it to PDF via the
    # browser's print function — or export as a standalone HTML report
    # that looks identical to a PDF when printed.
    html_path = output_path.replace(".pdf", ".html")
    _generate_html_report(history, meta, html_path)

    return True, (
        f"Report exported to: {html_path}\n"
        f"  Open in browser → File → Print → Save as PDF\n"
        f"  Or just share the HTML — it looks identical\n"
        f"  Files tracked: {len(history['files'])}\n"
        f"  Total versions: {sum(len(d['versions']) for d in history['files'].values())}"
    )

def _generate_html_report(history, meta, output_path):
    """Generate a clean, printable HTML report"""
    now        = datetime.now().strftime("%Y-%m-%d %H:%M")
    proj_name  = meta.get("project_name", "DataVault Project")
    created_at = meta.get("created_at", "")[:19].replace("T", " ")
    created_by = meta.get("created_by", "unknown")

    # Build file sections
    file_sections = []
    for filename, data in history["files"].items():
        versions = data["versions"]
        rows     = []
        for v in reversed(versions):
            timestamp = v["timestamp"][:19].replace("T", " ")
            tags      = v.get("tags", [])
            tag_html  = ""
            if tags:
                tag_html = "".join(
                    f'<span class="tag">{t["message"]}</span>' for t in tags
                )
            rows.append(f"""
            <tr>
              <td><strong>{v["version_id"]}</strong></td>
              <td>{timestamp}</td>
              <td>{v.get("author", "—")}</td>
              <td>{v["message"]}</td>
              <td class="hash">{v["hash"][:24]}…</td>
              <td>{_format_size(v["size_bytes"])}</td>
              <td>{tag_html or "—"}</td>
            </tr>""")

        file_sections.append(f"""
        <div class="file-section">
          <div class="file-header">
            <span class="file-name">{filename}</span>
            <span class="version-count">{len(versions)} version(s)</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Version</th><th>Timestamp</th><th>Author</th>
                <th>Message</th><th>Hash</th><th>Size</th><th>Tags</th>
              </tr>
            </thead>
            <tbody>{"".join(rows)}</tbody>
          </table>
        </div>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DataVault Report — {proj_name}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          font-size: 13px; color: #1a1a1a; background: #fff; padding: 40px; }}
  .header {{ border-bottom: 2px solid #1a1a1a; padding-bottom: 20px; margin-bottom: 32px; }}
  .header h1 {{ font-size: 22px; font-weight: 600; margin-bottom: 6px; }}
  .meta {{ color: #555; font-size: 12px; display: flex; gap: 24px; margin-top: 8px; }}
  .meta span {{ display: flex; align-items: center; gap: 4px; }}
  .file-section {{ margin-bottom: 36px; }}
  .file-header {{ display: flex; align-items: baseline; gap: 12px;
                  margin-bottom: 10px; padding-bottom: 6px;
                  border-bottom: 1px solid #e0e0e0; }}
  .file-name {{ font-size: 15px; font-weight: 600; color: #1a1a1a; }}
  .version-count {{ font-size: 12px; color: #888; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ background: #f5f5f5; padding: 8px 10px; text-align: left;
        font-weight: 500; color: #444; border-bottom: 1px solid #ddd; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
  .hash {{ font-family: 'Courier New', monospace; font-size: 11px; color: #666; }}
  .tag {{ display: inline-block; background: #e8f4e8; color: #2d6a2d;
          padding: 2px 8px; border-radius: 10px; font-size: 11px;
          margin: 1px 2px; border: 1px solid #b8d8b8; }}
  .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e0e0e0;
             color: #999; font-size: 11px; display: flex; justify-content: space-between; }}
  .integrity-banner {{ background: #e8f4e8; border: 1px solid #b8d8b8;
                       border-radius: 6px; padding: 12px 16px; margin-bottom: 28px;
                       font-size: 12px; color: #2d6a2d; }}
  @media print {{
    body {{ padding: 20px; }}
    .file-section {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>DataVault Provenance Report</h1>
  <div style="font-size:15px;color:#444;margin-top:4px">{proj_name}</div>
  <div class="meta">
    <span>Created by: {created_by}</span>
    <span>Project started: {created_at}</span>
    <span>Report generated: {now}</span>
    <span>Files tracked: {len(history["files"])}</span>
  </div>
</div>

<div class="integrity-banner">
  ✓ This report was generated by DataVault. Every version listed below is
  cryptographically fingerprinted with SHA-256. Any modification to a tracked
  file after its commit would produce a different hash and would be detectable
  via <code>datavault verify</code>.
</div>

{"".join(file_sections)}

<div class="footer">
  <span>Generated by DataVault — data provenance tool</span>
  <span>Report date: {now}</span>
</div>

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# ── Tagging ──────────────────────────────────────────────────

def tag_version(filepath, version_id, tag_message):
   
    _check_initialized()
    history  = _read_history()
    filename = os.path.basename(filepath)

    if filename not in history["files"]:
        return False, f"'{filename}' is not tracked."

    versions = history["files"][filename]["versions"]
    target   = next((v for v in versions if v["version_id"] == version_id), None)

    if not target:
        available = ", ".join(v["version_id"] for v in versions)
        return False, f"Version '{version_id}' not found. Available: {available}"

    # Add tags list if it doesn't exist yet
    if "tags" not in target:
        target["tags"] = []

    target["tags"].append({
        "message":    tag_message,
        "tagged_at":  datetime.now().isoformat(),
        "tagged_by":  _get_author()
    })

    _write_history(history)

    return True, (
        f"Tagged '{filename}' {version_id}\n"
        f"  Tag:    {tag_message}\n"
        f"  By:     {_get_author()}\n"
        f"  At:     {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

def list_tags(filepath):
    """Show all tags across all versions of a file"""
    _check_initialized()
    history  = _read_history()
    filename = os.path.basename(filepath)

    if filename not in history["files"]:
        return False, f"'{filename}' is not tracked."

    versions = history["files"][filename]["versions"]
    tagged   = [(v, t) for v in versions for t in v.get("tags", [])]

    if not tagged:
        return True, f"No tags found for '{filename}'. Use 'tag' to add one."

    lines = [f"\nTags for '{filename}':\n" + "─"*50]
    for version, tag in tagged:
        tagged_at = tag["tagged_at"][:19].replace("T", " ")
        lines.append(
            f"\n  {version['version_id']}  →  {tag['message']}\n"
            f"  Tagged by {tag['tagged_by']} on {tagged_at}"
        )
    return True, "\n".join(lines)


# ── Internal helpers ─────────────────────────────────────────

def _check_initialized():
    if not os.path.exists(VAULT_DIR):
        raise SystemExit("No DataVault project found. Run 'datavault init <name>' first.")

def _read_history():
    return _read_json(HISTORY_FILE)

def _write_history(data):
    _write_json(HISTORY_FILE, data)

def _version_path(filename, version_id):
    """Where a specific version of a file is stored"""
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return os.path.join(VERSIONS_DIR, f"{safe_name}__{version_id}")

def _get_author():
    return os.getenv("USERNAME") or os.getenv("USER") or "unknown"

def _format_size(bytes_count):
    if bytes_count < 1024:
        return f"{bytes_count} B"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count/1024:.1f} KB"
    else:
        return f"{bytes_count/1024/1024:.1f} MB"

def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)