# DataVault

**Cryptographic proof of data integrity for regulated AI.**

When an AI system makes a decision that affects someone's life — medical, legal, financial — regulators will ask three questions:

- Where did the training data come from?
- Who approved it?
- Has it been modified since?

DataVault answers all three with cryptographic proof. Zero dependencies. Pure Python stdlib.

---

## The problem

The EU AI Act (2024) requires organizations deploying high-risk AI systems to maintain verifiable records of their training data — its origin, modification history, and approval chain. Existing tools don't solve this:

- **Git** — not designed for large data files, no tamper detection, no approval workflow
- **DVC** — excellent for versioning, but cannot cryptographically prove data integrity to external auditors
- **Nothing** — provides audit-ready proof that your training data hasn't been modified since approval

DataVault fills this gap.

---

## What DataVault provides

| Requirement | How DataVault addresses it |
|---|---|
| Data origin tracking | Every file version is logged with author, timestamp, and commit message |
| Tamper detection | SHA-256 fingerprint on every version — any modification is detected instantly |
| Immutable history | Cryptographic hash chain — deleting or reordering versions breaks the chain |
| Approval workflow | Multi-user signing with reviewer, approver, and owner roles |
| Audit documentation | Export a complete provenance report as HTML/PDF |

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

# Sign a version for the approval workflow
python datavault.py sign training_data.csv v3 alice reviewer
python datavault.py sign training_data.csv v3 bob approver
python datavault.py approve training_data.csv v3

# Verify the full cryptographic chain
python datavault.py chain training_data.csv

# See exactly which rows changed between versions (CSV only)
python datavault.py rowdiff training_data.csv v1 v3

# Generate a full EU AI Act audit report
python datavault.py audit training_data.csv

# Export a provenance report
python datavault.py export

# Open the web dashboard
python datavault.py dashboard
```

---

## All commands

| Command | Description |
|---|---|
| `init <name>` | Initialize a new project |
| `add <file> "msg"` | Start tracking a file |
| `commit <file> "msg"` | Save a new version |
| `log <file>` | Show version history |
| `status` | Show all tracked files |
| `verify <file>` | Cryptographic tamper detection |
| `diff <file> v1 v2` | Text diff between versions |
| `checkout <file> v1` | Restore a version |
| `rowlog <file>` | Row change statistics (CSV) |
| `rowdiff <file> v1 v2` | Which rows were added, deleted, moved (CSV) |
| `rowhistory <file> col val` | Full history of one specific row |
| `chain <file>` | Verify the full cryptographic chain |
| `chainshow <file>` | Display chain visually |
| `sign <file> v <name> [role]` | Sign a version |
| `signatures <file>` | List or verify signatures |
| `approve <file> v` | Check approval status |
| `tag <file> v "label"` | Label a version |
| `audit <file>` | Generate EU AI Act audit report (chain + signatures + file status) |
| `export` | Export HTML/PDF provenance report |
| `dashboard` | Open local web dashboard |

---

## How it works

**SHA-256 tamper detection** — every version gets a 64-character fingerprint. Change one character anywhere in the file and `verify` catches it instantly, even months later.

**Hash chain** — each version's hash includes the previous version's hash. You cannot delete or reorder any version without breaking the chain. `chain` verifies the full sequence back to genesis — the same principle used in Bitcoin.

**Row-level CSV tracking** — `rowdiff v1 v3` shows exactly which rows were added, deleted, or moved between versions, not just that the file changed.

**Multi-user signing** — signatures are cryptographically tied to the file hash. Modify the file after signing and the signature is automatically invalidated.

---

## Files

| File | Purpose |
|---|---|
| `datavault.py` | CLI entrypoint |
| `vault_core.py` | Core engine — hashing, versioning, storage |
| `row_tracker.py` | Row-level CSV tracking |
| `chain.py` | Cryptographic hash chain |
| `signing.py` | Multi-user signing and approval |
| `dashboard.py` | Local web dashboard (port 5000) |
| `pi_bridge.py` | Auto-commit sensor data from Raspberry Pi cluster |
| `audit.py` | EU AI Act audit report generator |
| `migrate.py` | Backfill snapshots for existing versions |
| `test_datavault.py` | Full demo — run this first |

---

## EU AI Act relevance

DataVault directly supports compliance with:

The `audit` command runs all checks at once — chain integrity, file tamper detection, and signature verification — and generates an HTML report citing the relevant EU AI Act articles. Open in browser and print as PDF to share with auditors.

- **Article 10** — data governance and management practices for high-risk AI systems
- **Article 12** — record-keeping and logging requirements
- **Article 13** — transparency and provision of information to users

DataVault is not a legal compliance tool and does not guarantee regulatory compliance. It provides the technical infrastructure — cryptographic provenance records — that compliance requires.

---

## Requirements

- Python 3.6+

---

## Copyright

Copyright © 2026 Thi Minh Khuê Dao. All rights reserved.

This project and its source code are public for portfolio and evaluation purposes only.
No permission is granted to copy, distribute, modify, or use this code for any other purpose without explicit written permission.