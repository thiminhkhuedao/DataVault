import hashlib
import json
import os
import urllib.request
import urllib.error
from datetime import datetime

HISTORY_FILE        = ".datavault/history.json"
REMOTE_LINEAGE_FILE = ".datavault/remote_lineage.json"


def link_remote(local_file, remote_url, remote_file, declared_hash, message=""):
    """
    Declare that a local tracked file was derived from a file
    in a remote GitHub repository.

    Verifies that the declared hash matches the actual file on GitHub
    at the time of linking, then stores the reference permanently.

    Usage:
      datavault link-remote training_data.csv
        --repo https://github.com/user/medical-data
        --file raw_scans.csv
        --hash 542c990c4b807b81...
    """
    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    local_name = os.path.basename(local_file)
    if local_name not in history.get("files", {}):
        return False, f"'{local_name}' is not tracked. Use 'add' first."

    # Parse GitHub URL
    parsed = _parse_github_url(remote_url)
    if not parsed:
        return False, (
            f"Could not parse GitHub URL: {remote_url}\n"
            f"  Expected format: https://github.com/<owner>/<repo>"
        )

    owner, repo = parsed

    # Try to fetch the remote file and verify hash
    print(f"  Fetching remote file to verify hash...")
    raw_url    = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{remote_file}"
    actual_hash, fetch_error = _fetch_and_hash(raw_url)

    if fetch_error:
        # Try 'master' branch if 'main' fails
        raw_url_master = f"https://raw.githubusercontent.com/{owner}/{repo}/master/{remote_file}"
        actual_hash, fetch_error2 = _fetch_and_hash(raw_url_master)
        if fetch_error2:
            print(f"  ⚠ Could not fetch remote file: {fetch_error}")
            print(f"  Storing reference without hash verification.")
            actual_hash    = None
            hash_verified  = False
        else:
            raw_url       = raw_url_master
            hash_verified = True
    else:
        hash_verified = True

    # Verify hash if we fetched the file
    if hash_verified and actual_hash:
        if declared_hash and declared_hash != actual_hash:
            return False, (
                f"Hash mismatch — remote file does not match declared hash.\n"
                f"  Declared: {declared_hash[:32]}...\n"
                f"  Actual:   {actual_hash[:32]}...\n\n"
                f"  The remote file may have changed since you copied it.\n"
                f"  Use the actual hash: {actual_hash}"
            )
        if not declared_hash:
            declared_hash = actual_hash

    # Store the remote link
    remote_lineage = _load_remote_lineage()
    if local_name not in remote_lineage:
        remote_lineage[local_name] = {"remote_sources": []}

    # Check for existing link to same repo/file
    existing = next(
        (s for s in remote_lineage[local_name]["remote_sources"]
         if s["repo_owner"] == owner and s["repo_name"] == repo and s["remote_file"] == remote_file),
        None
    )

    entry = {
        "repo_owner":    owner,
        "repo_name":     repo,
        "repo_url":      remote_url,
        "remote_file":   remote_file,
        "raw_url":       raw_url,
        "declared_hash": declared_hash or "not verified",
        "hash_verified": hash_verified,
        "linked_at":     datetime.now().isoformat(),
        "linked_by":     os.getenv("USERNAME") or os.getenv("USER") or "unknown",
        "message":       message or ""
    }

    if existing:
        idx = remote_lineage[local_name]["remote_sources"].index(existing)
        remote_lineage[local_name]["remote_sources"][idx] = entry
        action = "Updated"
    else:
        remote_lineage[local_name]["remote_sources"].append(entry)
        action = "Linked"

    _save_remote_lineage(remote_lineage)

    return True, (
        f"{action} '{local_name}' to remote source\n"
        f"  Repo:     {owner}/{repo}\n"
        f"  File:     {remote_file}\n"
        f"  Hash:     {(declared_hash or 'not verified')[:32]}{'...' if declared_hash else ''}\n"
        f"  Verified: {'✓ hash matches remote file' if hash_verified and actual_hash == declared_hash else '⚠ not verified (file not accessible)'}\n"
        f"  Raw URL:  {raw_url}"
    )


def verify_remote(local_file):
    """
    Re-fetch all remote source files and check if their hashes
    still match what was declared at link time.

    Detects if a remote source has been modified since the link was created.
    """
    local_name     = os.path.basename(local_file)
    remote_lineage = _load_remote_lineage()

    if local_name not in remote_lineage:
        return True, f"No remote sources declared for '{local_name}'."

    sources = remote_lineage[local_name]["remote_sources"]
    if not sources:
        return True, f"No remote sources declared for '{local_name}'."

    lines     = [f"\nRemote source verification: '{local_name}'\n" + "─" * 55]
    all_valid = True

    for src in sources:
        print(f"  Checking {src['repo_owner']}/{src['repo_name']}/{src['remote_file']}...")
        current_hash, error = _fetch_and_hash(src["raw_url"])

        if error:
            lines.append(f"\n  ⚠ {src['repo_name']}/{src['remote_file']}")
            lines.append(f"    Could not fetch: {error}")
            lines.append(f"    Last known hash: {src['declared_hash'][:24]}...")
            all_valid = False
            continue

        if current_hash == src["declared_hash"]:
            linked_at = src["linked_at"][:19].replace("T", " ")
            lines.append(f"\n  ✓ {src['repo_name']}/{src['remote_file']}")
            lines.append(f"    Hash unchanged since {linked_at}")
            lines.append(f"    Hash: {current_hash[:32]}...")
        else:
            all_valid = False
            linked_at = src["linked_at"][:19].replace("T", " ")
            lines.append(f"\n  ✗ {src['repo_name']}/{src['remote_file']} — CHANGED")
            lines.append(f"    Linked at: {linked_at}")
            lines.append(f"    Declared:  {src['declared_hash'][:32]}...")
            lines.append(f"    Current:   {current_hash[:32]}...")
            lines.append(f"    ⚠ Remote source has been modified since this link was created.")
            lines.append(f"    Consider re-running your pipeline and re-linking.")

    lines.append(f"\n{'─' * 55}")
    lines.append(
        f"  {'✓ All remote sources unchanged' if all_valid else '✗ Some remote sources have changed'}"
    )
    return all_valid, "\n".join(lines)


def show_remote_lineage(local_file):
    """Display all remote sources declared for a file"""
    local_name     = os.path.basename(local_file)
    remote_lineage = _load_remote_lineage()

    if local_name not in remote_lineage or not remote_lineage[local_name]["remote_sources"]:
        return True, f"No remote sources declared for '{local_name}'.\nUse 'datavault link-remote' to declare one."

    sources = remote_lineage[local_name]["remote_sources"]
    lines   = [f"\nRemote sources: '{local_name}'\n" + "─" * 55]

    for src in sources:
        linked_at = src["linked_at"][:19].replace("T", " ")
        lines.append(f"\n  {src['repo_owner']}/{src['repo_name']}")
        lines.append(f"  File:     {src['remote_file']}")
        lines.append(f"  URL:      {src['repo_url']}")
        lines.append(f"  Hash:     {src['declared_hash'][:32]}...")
        lines.append(f"  Verified: {'✓' if src['hash_verified'] else '⚠ not verified'}")
        lines.append(f"  Linked:   {linked_at} by {src['linked_by']}")
        if src.get("message"):
            lines.append(f"  Note:     {src['message']}")

    lines.append(f"\n  Run 'datavault verify-remote {local_file}' to check if remote sources changed.")
    return True, "\n".join(lines)


def list_all_remote():
    """List all remote links across all files"""
    remote_lineage = _load_remote_lineage()

    if not remote_lineage:
        return True, "No remote links declared yet."

    lines = ["\nAll remote links:\n" + "─" * 55]
    for local_name, data in remote_lineage.items():
        for src in data.get("remote_sources", []):
            linked_at = src["linked_at"][:10]
            lines.append(
                f"\n  {local_name}\n"
                f"    ← {src['repo_owner']}/{src['repo_name']}/{src['remote_file']}\n"
                f"    linked {linked_at} · hash {'✓' if src['hash_verified'] else '?'}"
            )
    return True, "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────

def _parse_github_url(url):
    """Extract owner and repo from a GitHub URL"""
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    try:
        gh_idx = next(i for i, p in enumerate(parts) if "github.com" in p)
        owner  = parts[gh_idx + 1]
        repo   = parts[gh_idx + 2]
        return owner, repo
    except (StopIteration, IndexError):
        return None


def _fetch_and_hash(url):
    """Fetch a URL and return its SHA-256 hash"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DataVault/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            sha256 = hashlib.sha256()
            while chunk := response.read(65536):
                sha256.update(chunk)
            return sha256.hexdigest(), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return None, str(e.reason)
    except Exception as e:
        return None, str(e)


def _load_remote_lineage():
    if os.path.exists(REMOTE_LINEAGE_FILE):
        with open(REMOTE_LINEAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_remote_lineage(data):
    os.makedirs(os.path.dirname(REMOTE_LINEAGE_FILE), exist_ok=True)
    with open(REMOTE_LINEAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)