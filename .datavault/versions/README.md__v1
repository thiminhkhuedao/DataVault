# DataVault

**Cryptographic provenance and version control for AI training datasets.**

Git tracks code. DataVault tracks data — with SHA-256 tamper detection, row-level CSV diffing, cryptographic hash chains, and multi-user signing workflows.

Zero dependencies. Pure Python stdlib.

---

## Why not Git or DVC?

| | Git | DVC | DataVault |
|---|---|---|---|
| Tracks file versions | ✓ | ✓ | ✓ |
| Works on large files | ✗ | ✓ | ✓ |
| Row-level CSV diff | ✗ | ✗ | ✓ |
| Tamper detection (SHA-256) | partial | ✗ | ✓ |
| Cryptographic hash chain | ✓ | ✗ | ✓ |
| Multi-user signing & approval | ✗ | ✗ | ✓ |
| Zero dependencies | ✗ | ✗ | ✓ |

---

## Quickstart

```bash
# 1. Clone the repo
git clone https://github.com/thiminhkhuedao/DataVault.git
cd DataVault

# 2. Run the full demo (no setup needed)
python test_datavault.py
```

That's it. No pip install, no config, no database. Just Python 3.6+.

---

## Usage

```bash
# Initialize a project in any folder
python datavault.py init my-project

# Track a dataset
python datavault.py add training_data.csv "raw data from source"

# After editing the file, commit the change
python datavault.py commit training_data.csv "removed 42 duplicate rows"

# View full history
python datavault.py log training_data.csv

# Prove the file hasn't been tampered with
python datavault.py verify training_data.csv

# See which rows changed between versions (CSV only)
python datavault.py rowdiff training_data.csv v1 v3

# Verify the full cryptographic chain
python datavault.py chain training_data.csv

# Sign a version
python datavault.py sign training_data.csv v3 alice reviewer
python datavault.py sign training_data.csv v3 bob approver
python datavault.py approve training_data.csv v3

# Open the web dashboard
python datavault.py dashboard

# Export a provenance report (HTML → print as PDF)
python datavault.py export
```

---

## All commands

| Command | Description |
|---|---|
| `init <name>` | Start a new project |
| `add <file> "msg"` | Start tracking a file |
| `commit <file> "msg"` | Save a new version |
| `log <file>` | Show version history |
| `status` | Show all tracked files |
| `verify <file>` | Check for tampering |
| `diff <file> v1 v2` | Text diff between versions |
| `checkout <file> v1` | Restore a version |
| `tag <file> v2 "label"` | Label a version |
| `rowlog <file>` | Row change stats (CSV) |
| `rowdiff <file> v1 v2` | Which rows changed (CSV) |
| `rowhistory <file> col val` | History of one specific row |
| `chain <file>` | Verify cryptographic chain |
| `chainshow <file>` | Display chain visually |
| `sign <file> v <name> [role]` | Sign a version |
| `signatures <file> [v]` | List or verify signatures |
| `approve <file> v` | Check approval status |
| `export` | Export HTML/PDF report |
| `dashboard` | Open web dashboard |

---

## How it works

**SHA-256 hashing** — every version gets a 64-character fingerprint. Change one character anywhere in the file, the fingerprint changes completely. `verify` catches any modification made outside DataVault.

**Hash chain** — each version's hash includes the previous version's hash, like a blockchain. You cannot delete or reorder history without breaking the chain. `chain` verifies the full sequence back to genesis.

**Row-level tracking** — for CSV files, DataVault tracks individual rows, not just the whole file. `rowdiff v1 v3` shows exactly which rows were added, deleted, or moved between any two versions.

**Multi-user signing** — reviewers and approvers sign specific versions. Signatures are cryptographically tied to the file hash — if the file changes after signing, the signature is invalidated automatically.

**Pi Bridge** — optional module that connects DataVault to a Raspberry Pi cluster, automatically committing hourly power and temperature readings as tracked CSV files with anomaly detection and auto-tagging.

---

## Files

| File | Purpose |
|---|---|
| `datavault.py` | CLI entrypoint — the only file you run |
| `vault_core.py` | Core engine — hashing, versioning, storage |
| `row_tracker.py` | Row-level CSV diffing |
| `chain.py` | Cryptographic hash chain |
| `signing.py` | Multi-user signing and approval |
| `dashboard.py` | Local web dashboard (port 5000) |
| `pi_bridge.py` | Auto-commit sensor data from Raspberry Pi |
| `migrate.py` | Backfill snapshots for existing versions |
| `test_datavault.py` | Full demo — run this first |

---

## Requirements

- Python 3.6+
- Zero external dependencies — pure standard library

---

## Why this matters

When an AI system makes a wrong decision in a medical, legal, or financial context, regulators will ask: where did the training data come from? Who modified it? Which version was used? Today there is no standard tool that answers these questions reliably.

DataVault is a working prototype of that provenance layer.

---

## License

MIT
