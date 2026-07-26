#!/usr/bin/env python3
# ============================================================
# datavault.py — the main command line tool
#
#
# Usage:
#   python datavault.py init <project_name>
#   python datavault.py add <file> "<message>"
#   python datavault.py commit <file> "<message>"
#   python datavault.py log <file>
#   python datavault.py status
#   python datavault.py verify <file>
#   python datavault.py checkout <file> <version>
#   python datavault.py diff <file> <v1> <v2>
#   python datavault.py help
# ============================================================

import sys
import os

# Fix UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import vault_core as core
import row_tracker
import chain as chain_module
import signing


# ── Color output (makes terminal output readable) ────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(message):
    print(f"{GREEN}✓{RESET} {message}")

def err(message):
    print(f"{RED}✗{RESET} {message}")

def info(message):
    print(f"{BLUE}ℹ{RESET} {message}")


# ── Help text ────────────────────────────────────────────────

HELP = f"""
{BOLD}DataVault{RESET} — version control for datasets

{BOLD}COMMANDS:{RESET}

  {GREEN}init{RESET} <name>               Start a new DataVault project
  {GREEN}add{RESET} <file> "<message>"    Start tracking a new file
  {GREEN}commit{RESET} <file> "<message>" Save a new version of a tracked file
  {GREEN}log{RESET} <file>               Show version history of a file
  {GREEN}status{RESET}                   Show all tracked files and their status
  {GREEN}verify{RESET} <file>            Prove a file hasn't been tampered with
  {GREEN}checkout{RESET} <file> <v>      Restore file to a specific version (v1, v2...)
  {GREEN}diff{RESET} <file> <v1> <v2>   Show what changed between two versions
  {GREEN}tag{RESET} <file> <v> "<msg>"  Label a specific version with meaning
  {GREEN}tags{RESET} <file>             List all tags for a file
  {GREEN}export{RESET}                  Export full history as HTML/PDF report
  {GREEN}dashboard{RESET}               Open visual web dashboard in browser

{BOLD}ROW-LEVEL TRACKING (CSV files):{RESET}

  {GREEN}rowlog{RESET} <file>            Row change statistics across all versions
  {GREEN}rowdiff{RESET} <file> <v1> <v2> Which rows were added/deleted/moved
  {GREEN}rowhistory{RESET} <file> <col> <val>  Full history of one specific row

{BOLD}HASH CHAIN (tamper-proof history):{RESET}

  {GREEN}chain{RESET} <file>             Verify the full cryptographic chain
  {GREEN}chainshow{RESET} <file>         Display the chain visually
  {GREEN}chainbuild{RESET} <file>        Build/rebuild the chain for a file

{BOLD}SIGNATURES (multi-user approval):{RESET}

  {GREEN}sign{RESET} <file> <v> <name> [role]  Sign a version (roles: reviewer/approver/owner)
  {GREEN}signatures{RESET} <file> [version]    List or verify signatures
  {GREEN}approve{RESET} <file> <version>       Check if a version is fully approved

  {GREEN}help{RESET}                    Show this message

{BOLD}EXAMPLE WORKFLOW:{RESET}

  python datavault.py init my-ai-project
  python datavault.py add training_data.csv "raw data from source"
  # ... edit the CSV file ...
  python datavault.py commit training_data.csv "removed 42 duplicate rows"
  python datavault.py log training_data.csv
  python datavault.py verify training_data.csv
  python datavault.py diff training_data.csv v1 v2
  python datavault.py checkout training_data.csv v1

{BOLD}HOW IT WORKS:{RESET}

  Every file version is stored in .datavault/versions/
  Every commit is logged in .datavault/history.json
  Every file is fingerprinted with SHA-256 — if one character
  changes, the fingerprint changes, and verify catches it.
"""


# ── Command router ───────────────────────────────────────────

def main():
    args = sys.argv[1:]  # everything after "python datavault.py"
    
    if not args or args[0] == "help":
        print(HELP)
        return
    
    command = args[0].lower()
    
    # ── init ────────────────────────────────────────────────
    if command == "init":
        if len(args) < 2:
            err("Usage: python datavault.py init <project_name>")
            return
        success, message = core.init_project(args[1])
        ok(message) if success else err(message)
    
    # ── add ─────────────────────────────────────────────────
    elif command == "add":
        if len(args) < 3:
            err('Usage: python datavault.py add <file> "<message>"')
            return
        filepath = args[1]
        message  = " ".join(args[2:])
        success, result = core.add_file(filepath, message)
        ok(result) if success else err(result)
        if success:
            # Auto-trigger row snapshot (CSV files only)
            if row_tracker.snapshot_on_commit(filepath, "v1"):
                info("Row-level snapshot created (CSV detected)")
            # Auto-build hash chain
            chain_module.build_chain(os.path.basename(filepath))
            info("Hash chain updated")

    # ── commit ──────────────────────────────────────────────
    elif command == "commit":
        if len(args) < 3:
            err('Usage: python datavault.py commit <file> "<message>"')
            return
        filepath = args[1]
        message  = " ".join(args[2:])
        success, result = core.commit_file(filepath, message)
        ok(result) if success else err(result)
        if success:
            # Get the new version ID from history
            import json
            with open(core.HISTORY_FILE) as f:
                hist = json.load(f)
            fname    = os.path.basename(filepath)
            versions = hist["files"][fname]["versions"]
            new_vid  = versions[-1]["version_id"]
            # Auto row snapshot
            if row_tracker.snapshot_on_commit(filepath, new_vid):
                info("Row-level snapshot created (CSV detected)")
            # Auto chain update
            chain_module.build_chain(fname)
            info("Hash chain updated")
    
    # ── log ─────────────────────────────────────────────────
    elif command == "log":
        if len(args) < 2:
            err("Usage: python datavault.py log <file>")
            return
        success, result = core.get_log(args[1])
        print(result) if success else err(result)
    
    # ── status ──────────────────────────────────────────────
    elif command == "status":
        success, result = core.list_files()
        print(result) if success else err(result)
    
    # ── verify ──────────────────────────────────────────────
    elif command == "verify":
        if len(args) < 2:
            err("Usage: python datavault.py verify <file>")
            return
        success, result = core.verify_file(args[1])
        print(result) if success else err(result)
    
    # ── checkout ────────────────────────────────────────────
    elif command == "checkout":
        if len(args) < 3:
            err("Usage: python datavault.py checkout <file> <version>")
            err("Example: python datavault.py checkout data.csv v1")
            return
        success, result = core.checkout_version(args[1], args[2])
        ok(result) if success else err(result)
    
    # ── diff ────────────────────────────────────────────────
    elif command == "diff":
        if len(args) < 4:
            err("Usage: python datavault.py diff <file> <v1> <v2>")
            err("Example: python datavault.py diff data.csv v1 v2")
            return
        success, result = core.diff_versions(args[1], args[2], args[3])
        print(result) if success else err(result)
    
    # ── rowlog ──────────────────────────────────────────────
    elif command == "rowlog":
        if len(args) < 2:
            err("Usage: python datavault.py rowlog <file>")
            return
        success, result = row_tracker.row_stats(args[1])
        print(result) if success else err(result)

    # ── rowdiff ─────────────────────────────────────────────
    elif command == "rowdiff":
        if len(args) < 4:
            err("Usage: python datavault.py rowdiff <file> <v1> <v2>")
            return
        success, result = row_tracker.row_diff(args[1], args[2], args[3])
        print(result) if success else err(result)

    # ── rowhistory ───────────────────────────────────────────
    elif command == "rowhistory":
        if len(args) < 4:
            err("Usage: python datavault.py rowhistory <file> <column> <value>")
            err("Example: python datavault.py rowhistory data.csv id 7")
            return
        success, result = row_tracker.row_history(args[1], args[2], args[3])
        print(result) if success else err(result)

    # ── chain ────────────────────────────────────────────────
    elif command == "chain":
        if len(args) < 2:
            err("Usage: python datavault.py chain <file>")
            return
        filename        = os.path.basename(args[1])
        valid, results  = chain_module.verify_chain(filename)
        if isinstance(results, list):
            print(chain_module.format_chain_verification(filename, results))
        else:
            err(results)

    # ── chainshow ────────────────────────────────────────────
    elif command == "chainshow":
        if len(args) < 2:
            err("Usage: python datavault.py chainshow <file>")
            return
        filename       = os.path.basename(args[1])
        success, result = chain_module.display_chain(filename)
        print(result) if success else err(result)

    # ── chainbuild ───────────────────────────────────────────
    elif command == "chainbuild":
        if len(args) < 2:
            err("Usage: python datavault.py chainbuild <file>")
            return
        filename       = os.path.basename(args[1])
        success, result = chain_module.build_chain(filename)
        ok(f"Chain built for '{filename}' ({len(result)} version(s))") if success else err(result)

    # ── sign ─────────────────────────────────────────────────
    elif command == "sign":
        if len(args) < 4:
            err("Usage: python datavault.py sign <file> <version> <signer> [role]")
            err("Roles: reviewer, approver, owner, witness")
            err("Example: python datavault.py sign data.csv v2 alice approver")
            return
        filepath   = args[1]
        version_id = args[2]
        signer     = args[3]
        role       = args[4] if len(args) > 4 else "reviewer"
        success, result = signing.sign_version(filepath, version_id, signer, role)
        ok(result) if success else err(result)

    # ── signatures ───────────────────────────────────────────
    elif command == "signatures":
        if len(args) < 2:
            err("Usage: python datavault.py signatures <file> [version]")
            return
        if len(args) >= 3:
            success, result = signing.verify_signatures(args[1], args[2])
        else:
            success, result = signing.list_all_signatures(args[1])
        print(result) if success else err(result)

    # ── approve ──────────────────────────────────────────────
    elif command == "approve":
        if len(args) < 3:
            err("Usage: python datavault.py approve <file> <version>")
            return
        approved, result = signing.approval_status(args[1], args[2])
        print(result)

    # ── tag ─────────────────────────────────────────────────
    elif command == "tag":
        if len(args) < 4:
            err('Usage: python datavault.py tag <file> <version> "<message>"')
            err('Example: python datavault.py tag data.csv v2 "used for training 2026-07-25"')
            return
        filepath   = args[1]
        version_id = args[2]
        message    = " ".join(args[3:])
        success, result = core.tag_version(filepath, version_id, message)
        ok(result) if success else err(result)

    # ── tags ────────────────────────────────────────────────
    elif command == "tags":
        if len(args) < 2:
            err("Usage: python datavault.py tags <file>")
            return
        success, result = core.list_tags(args[1])
        print(result) if success else err(result)

    # ── export ──────────────────────────────────────────────
    elif command == "export":
        output = args[1] if len(args) > 1 else "datavault_report.pdf"
        success, result = core.export_pdf(output)
        ok(result) if success else err(result)

    # ── dashboard ────────────────────────────────────────────
    elif command == "dashboard":
        info("Starting dashboard — opening browser...")
        import dashboard as db_module
        db_module.main()

    # ── unknown command ──────────────────────────────────────
    else:
        err(f"Unknown command: '{command}'")
        info("Run 'python datavault.py help' to see all commands")


if __name__ == "__main__":
    main()