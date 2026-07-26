# DataVault
### Version control for datasets — like Git, but for data

---

## The problem

Git tracks changes to code perfectly. But AI training data — CSV files,
JSON datasets, image folders — has no equivalent. When something goes wrong
with an AI model, you can't answer basic questions:

- What did the training data look like 3 weeks ago?
- Who changed it and why?
- Has this file been tampered with since we last verified it?
- Which version of the data produced our best model?

DataVault solves this. Every change is logged, every version is stored,
every file is fingerprinted so tampering is detectable.

---

## How to use it

```bash
# Start a project
python datavault.py init my-ai-project

# Start tracking a dataset
python datavault.py add training_data.csv "raw data from source"

# After editing the file, log the change
python datavault.py commit training_data.csv "removed 42 duplicate rows"

# See full history
python datavault.py log training_data.csv

# See what changed between two versions
python datavault.py diff training_data.csv v1 v2

# Prove the file hasn't been tampered with
python datavault.py verify training_data.csv

# Restore an older version
python datavault.py checkout training_data.csv v1

# See all tracked files
python datavault.py status
```

---

## Run the full demo

```bash
python test_datavault.py
```

This runs a complete workflow: creates a dataset, commits 3 versions,
simulates tampering, catches it, and restores the clean version.

---

## How it works

**Hashing:** Every file version is fingerprinted with SHA-256.
If even one character changes, the fingerprint changes completely.
This is how `verify` catches tampering.

**Storage:** Every version is copied into `.datavault/versions/`
as a separate file. You never lose old data.

**History:** Every commit is logged in `.datavault/history.json`
with timestamp, author, message, hash, and file size.

---

## Files

| File | Purpose |
|---|---|
| `datavault.py` | The CLI tool you run |
| `vault_core.py` | The engine (hashing, storage, history) |
| `test_datavault.py` | Full demo of every feature |

---

## Why this matters

As AI gets embedded in medical, legal, and financial decisions,
regulators are starting to require proof of where training data
came from and that it hasn't been modified. DataVault is a minimal
working prototype of that provenance layer.

---

