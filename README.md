# DataVault

**Cryptographic proof of data integrity for regulated AI.**

When an AI system makes a decision that affects someone's life — medical, legal, financial — regulators will ask three questions:

- Where did the training data come from?
- Who approved it?
- Has it been modified since?

DataVault answers all three with cryptographic proof. Zero dependencies. Pure Python stdlib.

---

## The problem

The EU AI Act (2024) requires organizations deploying high-risk AI systems to maintain verifiable records of their training data. Existing tools don't solve this:

- **Git** — not designed for large data files, no tamper detection, no approval workflow
- **DVC** — excellent for versioning, but cannot cryptographically prove data integrity to external auditors
- **Nothing** — provides audit-ready proof that your training data hasn't been modified since approval

DataVault fills this gap.

---

## EU AI Act compliance reference

| Requirement | Article | How DataVault addresses it |
|---|---|---|
| Data governance | Art. 10 | Every version logged with author, timestamp, commit message |
| Tamper detection | Art. 10 | SHA-256 fingerprint — any modification detected instantly |
| Immutable history | Art. 12 | Cryptographic hash chain — history cannot be rewritten |
| Approval workflow | Art. 13 | Multi-user signing with reviewer, approver, owner roles |
| Audit documentation | Art. 13 | Export full provenance report as HTML/PDF |

*DataVault is not a legal compliance tool. It provides the technical infrastructure that compliance requires.*

---

## Quickstart

```bash
git clone https://github.com/thiminhkhuedao/DataVault.git
cd DataVault
python test_datavault.py
```

Or install via pip:

```bash
pip install datavault-cli
```

No config. No database. Python 3.6+ only.

---

## Usage

```bash
# Initialize a project
python datavault.py init my-project

# Track a dataset
python datavault.py add training_data.csv "raw data from source"

# Commit a change
python datavault.py commit training_data.csv "removed 42 duplicate rows"

# Prove the file hasn't been tampered with
python datavault.py verify training_data.csv

# Generate a full EU AI Act audit report
python datavault.py audit training_data.csv

# See which rows changed between versions (CSV only)
python datavault.py rowdiff training_data.csv v1 v3

# Semantic diff — analyze the meaning of changes
python datavault.py diff training_data.csv v1 v3 --semantic

# Statistical comparison between versions
python datavault.py compare training_data.csv v1 v3 --statistical

# Detect data quality issues
python datavault.py anomaly training_data.csv

# Freeze a version (no further commits without unfreezing)
python datavault.py freeze training_data.csv v3 "approved for production"

# Sign a version
python datavault.py sign training_data.csv v3 alice reviewer
python datavault.py sign training_data.csv v3 bob approver
python datavault.py approve training_data.csv v3

# Declare lineage (where did this data come from?)
python datavault.py link training_data.csv raw_data.csv labels.csv

# Declare remote lineage (from another GitHub repo)
# Windows PowerShell — all on one line:
python datavault.py link-remote training_data.csv --repo https://github.com/user/medical-data --file raw_scans.csv --hash abc123

# Mac/Linux — line continuation works:
python datavault.py link-remote training_data.csv \
  --repo https://github.com/user/medical-data \
  --file raw_scans.csv \
  --hash abc123

# Verify remote sources haven't changed
python datavault.py verify-remote training_data.csv

# Show remote sources for a file
python datavault.py remote-lineage training_data.csv

# List all remote links in the project
python datavault.py remote-links

# Watch files for unauthorized modifications in real time
python datavault.py watch training_data.csv

# Create an encryption key (generates a one-time recovery code)
python datavault.py keygen alice

# Encrypt a version
python datavault.py encrypt training_data.csv v3 alice

# Change passphrase
python datavault.py rekey alice

# Forgot passphrase? Use your recovery code
python datavault.py recover alice

# Verify the full cryptographic chain
python datavault.py chain training_data.csv

# Open the web dashboard
python datavault.py dashboard

# Export a provenance report (HTML/PDF)
python datavault.py export
```

---

## All commands

### Core versioning
| Command | Description |
|---|---|
| `init <name>` | Initialize a new project |
| `add <file> "msg"` | Start tracking a file |
| `commit <file> "msg"` | Save a new version |
| `log <file>` | Show version history |
| `status` | Show all tracked files |
| `verify <file>` | SHA-256 tamper detection |
| `diff <file> v1 v2` | Text diff between versions |
| `diff <file> v1 v2 --semantic` | Semantic diff — analyze meaning of changes |
| `checkout <file> v1` | Restore a version |

### Data analysis (CSV)
| Command | Description |
|---|---|
| `rowlog <file>` | Row change statistics per version |
| `rowdiff <file> v1 v2` | Which rows were added, deleted, moved |
| `rowhistory <file> col val` | Full history of one specific row |
| `compare <file> v1 v2 --statistical` | Deep statistical comparison between versions |
| `anomaly <file> [version]` | Detect data quality issues |

### Cryptographic chain
| Command | Description |
|---|---|
| `chain <file>` | Verify the full hash chain |
| `chainshow <file>` | Display chain visually |
| `chainbuild <file>` | Build/rebuild the chain |

### Approval workflow
| Command | Description |
|---|---|
| `sign <file> v <name> [role]` | Sign a version |
| `signatures <file>` | List or verify signatures |
| `approve <file> v` | Check approval status |
| `freeze <file> v ["reason"] [--method password\|signature]` | Lock a version |
| `unfreeze <file> v [--by <name>]` | Unlock a version |
| `frozen` | List all frozen versions |

### Lineage & provenance
| Command | Description |
|---|---|
| `link <output> <source1> [source2...]` | Declare local data dependencies |
| `lineage <file>` | Show full lineage tree |
| `lineages` | List all declared lineage |
| `link-remote <file> --repo <url> --file <f> [--hash <h>]` | Link to remote GitHub source |
| `verify-remote <file>` | Check if remote sources have changed |
| `remote-lineage <file>` | Show remote sources |

### Security
| Command | Description |
|---|---|
| `watch <file> [--interval N]` | Real-time tamper detection |
| `keygen <key>` | Create an encryption key — generates a one-time recovery code |
| `encrypt <file> v <key>` | Encrypt a version |
| `decrypt <file> v <key> [output]` | Decrypt a version |
| `rekey <key>` | Change passphrase for a key — re-encrypts all files automatically |
| `recover <key>` | Reset forgotten passphrase using one-time recovery code |
| `encrypted` | List encrypted versions |

### Reporting
| Command | Description |
|---|---|
| `audit <file>` | Generate EU AI Act audit report |
| `export` | Export HTML/PDF provenance report |
| `dashboard` | Open local web dashboard (port 5000) |
| `tag <file> v "label"` | Label a version |
| `migrate` | Backfill snapshots for existing versions |

---

## How it works

**SHA-256 tamper detection** — every version gets a 64-character fingerprint. Change one character anywhere and `verify` catches it.

**Hash chain** — each version's hash includes the previous version's hash. Delete or reorder any version and the chain breaks. Same principle as Bitcoin.

**Row-level tracking** — `rowdiff v1 v3` shows exactly which rows were added, deleted, or moved. Not just "the file changed".

**Semantic diff** — analyzes the *meaning* of changes. Mean drift, class imbalance shifts, distribution changes — not just raw line diffs.

**Multi-user signing** — signatures are cryptographically tied to the file hash. Modify the file after signing and the signature is invalidated automatically.

**Freeze** — lock a version with a passphrase or owner signature. Nobody can commit new versions without unfreezing.

**Lineage** — declare where your data came from, locally and across GitHub repos. Verify that sources haven't changed since you linked them.

**Watch mode** — continuous real-time monitoring. Alerts immediately on any unauthorized modification.

**Encryption** — encrypt specific versions with PBKDF2-derived keys. Pure Python, no dependencies.

---

## Files

| File | Purpose |
|---|---|
| `datavault.py` | CLI entrypoint |
| `vault_core.py` | Core engine — hashing, versioning, storage |
| `row_tracker.py` | Row-level CSV tracking |
| `chain.py` | Cryptographic hash chain |
| `signing.py` | Multi-user signing and approval |
| `freeze.py` | Version locking with passphrase or signature |
| `audit.py` | EU AI Act audit report generator |
| `semantic_diff.py` | Semantic analysis of dataset changes |
| `statistical_compare.py` | Statistical comparison between versions |
| `anomaly.py` | Data quality anomaly detection |
| `lineage.py` | Local data lineage tracking |
| `remote_lineage.py` | Cross-repo lineage via GitHub |
| `watch.py` | Real-time file monitoring |
| `encrypt.py` | Version encryption |
| `dashboard.py` | Local web dashboard (port 5000) |
| `pi_bridge.py` | Auto-commit sensor data from Raspberry Pi |
| `migrate.py` | Backfill snapshots for existing versions |
| `test_datavault.py` | Full demo — run this first |

---

## Requirements

- Python 3.6+
- Zero external dependencies — pure standard library

---

## Copyright

Copyright © 2026 Thi Minh Khuê Dao. All rights reserved.

This project and its source code are public for portfolio and evaluation purposes only.
No permission is granted to copy, distribute, modify, or use this code for any other purpose without explicit written permission.