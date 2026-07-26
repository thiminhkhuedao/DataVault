# ============================================================
# migrate.py — backfill row snapshots + hash chain
#
# Run once: python migrate.py
# ============================================================

import json
import os
import shutil
import row_tracker
import chain as chain_module

VAULT_DIR    = ".datavault"
HISTORY_FILE = ".datavault/history.json"
VERSIONS_DIR = ".datavault/versions"

def migrate():
    if not os.path.exists(HISTORY_FILE):
        print("No DataVault project found.")
        return

    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)

    print("DataVault migration — backfilling row snapshots + hash chain\n")

    for filename, data in history["files"].items():
        versions = data["versions"]
        print(f"File: {filename} ({len(versions)} version(s))")

        for v in versions:
            version_id = v["version_id"]

            # Find the stored version file in .datavault/versions/
            safe_name    = filename.replace("/", "_").replace("\\", "_")
            stored_path  = os.path.join(VERSIONS_DIR, f"{safe_name}__{version_id}")

            if not os.path.exists(stored_path):
                print(f"  {version_id}: stored file not found, skipping")
                continue

            # Generate row snapshot from stored file (not current file)
            if filename.lower().endswith(".csv"):
                snapshot, headers = row_tracker.build_row_snapshot(stored_path)
                if snapshot:
                    row_tracker.save_row_snapshot(filename, version_id, snapshot, headers)
                    print(f"  {version_id}: row snapshot created ({len(snapshot)} rows)")
                else:
                    print(f"  {version_id}: empty CSV, skipped")
            else:
                print(f"  {version_id}: not a CSV, skipping row snapshot")

        # Build hash chain for this file
        success, result = chain_module.build_chain(filename)
        if success:
            print(f"  Chain built ({len(result)} blocks)")
        else:
            print(f"  Chain failed: {result}")

        print()

    print("Migration complete.")
    print("\nNow try:")
    print("  python datavault.py rowlog training_data.csv")
    print("  python datavault.py rowdiff training_data.csv v1 v3")
    print("  python datavault.py chain training_data.csv")
    print("  python datavault.py chainshow training_data.csv")

if __name__ == "__main__":
    migrate()