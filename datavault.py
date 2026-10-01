#!/usr/bin/env python3
import sys
import os

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import vault_core as core
import row_tracker
import chain as chain_module
import signing

GREEN  = "\033[92m"
RED    = "\033[91m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(message):  print(f"{GREEN}✓{RESET} {message}")
def err(message): print(f"{RED}✗{RESET} {message}")
def info(message):print(f"{BLUE}ℹ{RESET} {message}")

HELP = f"""
{BOLD}DataVault{RESET} — version control for datasets

{BOLD}COMMANDS:{RESET}
  {GREEN}init{RESET} <name>                        Start a new project
  {GREEN}add{RESET} <file> "<message>"             Start tracking a file
  {GREEN}commit{RESET} <file> "<message>"          Save a new version
  {GREEN}log{RESET} <file>                         Show version history
  {GREEN}status{RESET}                             Show all tracked files
  {GREEN}verify{RESET} <file>                      Check for tampering
  {GREEN}checkout{RESET} <file> <v>                Restore a version
  {GREEN}diff{RESET} <file> <v1> <v2>              Show text diff
  {GREEN}tag{RESET} <file> <v> "<msg>"             Label a version
  {GREEN}tags{RESET} <file>                        List all tags
  {GREEN}export{RESET}                             Export HTML/PDF report
  {GREEN}dashboard{RESET}                          Open web dashboard

{BOLD}ROW-LEVEL (CSV):{RESET}
  {GREEN}rowlog{RESET} <file>                      Row change statistics
  {GREEN}rowdiff{RESET} <file> <v1> <v2>           Which rows changed
  {GREEN}rowhistory{RESET} <file> <col> <val>       History of one row

{BOLD}HASH CHAIN:{RESET}
  {GREEN}chain{RESET} <file>                       Verify chain
  {GREEN}chainshow{RESET} <file>                   Display chain visually
  {GREEN}chainbuild{RESET} <file>                  Build/rebuild chain

{BOLD}SIGNATURES:{RESET}
  {GREEN}sign{RESET} <file> <v> <name> [role]      Sign a version
  {GREEN}signatures{RESET} <file> [version]         List or verify signatures
  {GREEN}approve{RESET} <file> <version>            Check approval status
  {GREEN}help{RESET}                               Show this message
"""

def main():
    args = sys.argv[1:]
    if not args or args[0] == "help":
        print(HELP)
        return

    command = args[0].lower()

    if command == "init":
        if len(args) < 2:
            err("Usage: python datavault.py init <project_name>"); return
        success, message = core.init_project(args[1])
        ok(message) if success else err(message)

    elif command == "add":
        if len(args) < 3:
            err('Usage: python datavault.py add <file> "<message>"'); return
        filepath, message = args[1], " ".join(args[2:])
        success, result = core.add_file(filepath, message)
        ok(result) if success else err(result)
        if success:
            if row_tracker.snapshot_on_commit(filepath, "v1"):
                info("Row-level snapshot created")
            chain_module.build_chain(os.path.basename(filepath))
            info("Hash chain updated")

    elif command == "commit":
        if len(args) < 3:
            err('Usage: python datavault.py commit <file> "<message>"'); return
        filepath, message = args[1], " ".join(args[2:])
        success, result = core.commit_file(filepath, message)
        ok(result) if success else err(result)
        if success:
            import json
            with open(core.HISTORY_FILE) as f:
                hist = json.load(f)
            fname   = os.path.basename(filepath)
            new_vid = hist["files"][fname]["versions"][-1]["version_id"]
            if row_tracker.snapshot_on_commit(filepath, new_vid):
                info("Row-level snapshot created")
            chain_module.build_chain(fname)
            info("Hash chain updated")

    elif command == "log":
        if len(args) < 2:
            err("Usage: python datavault.py log <file>"); return
        success, result = core.get_log(args[1])
        print(result) if success else err(result)

    elif command == "status":
        success, result = core.list_files()
        print(result) if success else err(result)

    elif command == "verify":
        if len(args) < 2:
            err("Usage: python datavault.py verify <file>"); return
        success, result = core.verify_file(args[1])
        print(result) if success else err(result)

    elif command == "checkout":
        if len(args) < 3:
            err("Usage: python datavault.py checkout <file> <version>"); return
        success, result = core.checkout_version(args[1], args[2])
        ok(result) if success else err(result)

    elif command == "diff":
        if len(args) < 4:
            err("Usage: python datavault.py diff <file> <v1> <v2>"); return
        success, result = core.diff_versions(args[1], args[2], args[3])
        print(result) if success else err(result)

    elif command == "rowlog":
        if len(args) < 2:
            err("Usage: python datavault.py rowlog <file>"); return
        success, result = row_tracker.row_stats(args[1])
        print(result) if success else err(result)

    elif command == "rowdiff":
        if len(args) < 4:
            err("Usage: python datavault.py rowdiff <file> <v1> <v2>"); return
        success, result = row_tracker.row_diff(args[1], args[2], args[3])
        print(result) if success else err(result)

    elif command == "rowhistory":
        if len(args) < 4:
            err("Usage: python datavault.py rowhistory <file> <column> <value>"); return
        success, result = row_tracker.row_history(args[1], args[2], args[3])
        print(result) if success else err(result)

    elif command == "chain":
        if len(args) < 2:
            err("Usage: python datavault.py chain <file>"); return
        filename = os.path.basename(args[1])
        valid, results = chain_module.verify_chain(filename)
        print(chain_module.format_chain_verification(filename, results)) if isinstance(results, list) else err(results)

    elif command == "chainshow":
        if len(args) < 2:
            err("Usage: python datavault.py chainshow <file>"); return
        success, result = chain_module.display_chain(os.path.basename(args[1]))
        print(result) if success else err(result)

    elif command == "chainbuild":
        if len(args) < 2:
            err("Usage: python datavault.py chainbuild <file>"); return
        filename = os.path.basename(args[1])
        success, result = chain_module.build_chain(filename)
        ok(f"Chain built for '{filename}' ({len(result)} version(s))") if success else err(result)

    elif command == "sign":
        if len(args) < 4:
            err("Usage: python datavault.py sign <file> <version> <signer> [role]"); return
        role = args[4] if len(args) > 4 else "reviewer"
        success, result = signing.sign_version(args[1], args[2], args[3], role)
        ok(result) if success else err(result)

    elif command == "signatures":
        if len(args) < 2:
            err("Usage: python datavault.py signatures <file> [version]"); return
        if len(args) >= 3:
            success, result = signing.verify_signatures(args[1], args[2])
        else:
            success, result = signing.list_all_signatures(args[1])
        print(result) if success else err(result)

    elif command == "approve":
        if len(args) < 3:
            err("Usage: python datavault.py approve <file> <version>"); return
        _, result = signing.approval_status(args[1], args[2])
        print(result)

    elif command == "tag":
        if len(args) < 4:
            err('Usage: python datavault.py tag <file> <version> "<message>"'); return
        success, result = core.tag_version(args[1], args[2], " ".join(args[3:]))
        ok(result) if success else err(result)

    elif command == "tags":
        if len(args) < 2:
            err("Usage: python datavault.py tags <file>"); return
        success, result = core.list_tags(args[1])
        print(result) if success else err(result)

    elif command == "export":
        output = args[1] if len(args) > 1 else "datavault_report.pdf"
        success, result = core.export_pdf(output)
        ok(result) if success else err(result)

    elif command == "dashboard":
        import dashboard as db_module
        db_module.main()

    else:
        err(f"Unknown command: '{command}'")
        info("Run 'python datavault.py help' to see all commands")

if __name__ == "__main__":
    main()