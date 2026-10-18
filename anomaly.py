import csv
import json
import os
import math
import statistics

HISTORY_FILE = ".datavault/history.json"
VERSIONS_DIR = ".datavault/versions"


def detect_anomalies(filepath, version_id=None):
    """
    Analyze a specific version of a CSV file (or the current file)
    for data quality issues common in AI training datasets.

    Checks:
    - Missing values per column
    - Duplicate rows
    - Class imbalance (categorical columns)
    - Outliers (numeric columns, using IQR method)
    - Constant columns (zero variance — useless for training)
    - Column type inconsistencies (mixed numeric/text)
    - Suspicious value patterns (negative ages, future dates, etc.)
    """
    filename = os.path.basename(filepath)

    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    # Decide which file to read
    if version_id:
        safe_name = filename.replace("/", "_").replace("\\", "_")
        read_path = os.path.join(VERSIONS_DIR, f"{safe_name}__{version_id}")
        if not os.path.exists(read_path):
            return False, f"No stored file for version '{version_id}'."
        label = version_id
    else:
        if not os.path.exists(filepath):
            return False, f"File not found: {filepath}"
        read_path = filepath
        versions  = history["files"][filename]["versions"]
        label     = versions[-1]["version_id"] + " (current)"

    rows = _read_csv(read_path)
    if not rows:
        return False, "Could not read CSV — file is empty or not valid CSV."

    headers = list(rows[0].keys())
    n       = len(rows)

    lines = [
        f"\nAnomaly detection: '{filename}' ({label})",
        "─" * 60,
        f"  Rows: {n}  |  Columns: {len(headers)}",
        ""
    ]

    all_findings = []

    # ── 1. Missing values ──────────────────────────────────────
    missing_findings = []
    for col in headers:
        empty = sum(1 for r in rows if r.get(col) in (None, "", "nan", "NULL", "null", "N/A", "n/a"))
        if empty > 0:
            pct = empty / n * 100
            severity = 3 if pct > 30 else 2 if pct > 10 else 1
            missing_findings.append((col, empty, pct, severity))

    if missing_findings:
        missing_findings.sort(key=lambda x: x[2], reverse=True)
        all_findings.append({
            "category": "MISSING VALUES",
            "severity": max(f[3] for f in missing_findings),
            "items": [
                f"'{col}': {empty} missing ({pct:.1f}%){' ← HIGH' if sev == 3 else ' ← MEDIUM' if sev == 2 else ''}"
                for col, empty, pct, sev in missing_findings
            ]
        })

    # ── 2. Duplicate rows ──────────────────────────────────────
    row_strs   = [json.dumps(r, sort_keys=True) for r in rows]
    seen       = set()
    duplicates = 0
    for s in row_strs:
        if s in seen:
            duplicates += 1
        seen.add(s)

    if duplicates > 0:
        pct      = duplicates / n * 100
        severity = 3 if pct > 10 else 2 if pct > 2 else 1
        all_findings.append({
            "category": "DUPLICATE ROWS",
            "severity": severity,
            "items": [f"{duplicates} duplicate row(s) found ({pct:.1f}% of dataset)"]
        })

    # ── 3. Per-column analysis ─────────────────────────────────
    for col in headers:
        values = [r[col] for r in rows if r.get(col) not in (None, "", "nan", "NULL", "null", "N/A", "n/a")]
        if not values:
            continue

        col_type = _detect_type(values)

        if col_type == "numeric":
            nums = []
            for v in values:
                try:
                    nums.append(float(v))
                except ValueError:
                    pass

            if len(nums) < 2:
                continue

            # Constant column
            if min(nums) == max(nums):
                all_findings.append({
                    "category": f"CONSTANT COLUMN — '{col}'",
                    "severity": 2,
                    "items": [f"All {len(nums)} values are identical: {nums[0]}", "Zero variance — useless feature for training"]
                })
                continue

            # Outliers using IQR
            sorted_nums = sorted(nums)
            q1  = sorted_nums[len(sorted_nums) // 4]
            q3  = sorted_nums[3 * len(sorted_nums) // 4]
            iqr = q3 - q1

            if iqr > 0:
                lower = q1 - 3 * iqr
                upper = q3 + 3 * iqr
                outliers = [v for v in nums if v < lower or v > upper]
                if outliers:
                    pct      = len(outliers) / len(nums) * 100
                    severity = 2 if pct > 5 else 1
                    all_findings.append({
                        "category": f"OUTLIERS — '{col}'",
                        "severity": severity,
                        "items": [
                            f"{len(outliers)} outlier(s) detected ({pct:.1f}%)",
                            f"Expected range: [{lower:.2f}, {upper:.2f}]  (3×IQR method)",
                            f"Outlier values: {sorted(outliers)[:5]}" + (" ..." if len(outliers) > 5 else "")
                        ]
                    })

            # Negative values in suspicious columns
            col_lower = col.lower()
            if any(k in col_lower for k in ["age", "count", "quantity", "price", "amount", "score", "id"]):
                negatives = [v for v in nums if v < 0]
                if negatives:
                    all_findings.append({
                        "category": f"SUSPICIOUS VALUES — '{col}'",
                        "severity": 3,
                        "items": [
                            f"{len(negatives)} negative value(s) in '{col}' column",
                            f"Values: {negatives[:5]}" + (" ..." if len(negatives) > 5 else ""),
                            "Negative values unexpected for this column type"
                        ]
                    })

            # Type inconsistency
            non_numeric = [v for v in values if not _is_numeric(v)]
            if non_numeric and len(non_numeric) < len(values) * 0.5:
                all_findings.append({
                    "category": f"TYPE INCONSISTENCY — '{col}'",
                    "severity": 2,
                    "items": [
                        f"Mostly numeric but {len(non_numeric)} non-numeric value(s) found",
                        f"Examples: {non_numeric[:3]}"
                    ]
                })

        else:
            # Categorical: class imbalance
            dist     = {}
            for v in values:
                dist[v] = dist.get(v, 0) + 1

            n_cats = len(dist)
            if n_cats == 1:
                all_findings.append({
                    "category": f"CONSTANT COLUMN — '{col}'",
                    "severity": 2,
                    "items": [f"Only one category: '{list(dist.keys())[0]}'", "Zero variance — useless feature for training"]
                })
                continue

            if n_cats <= 20:
                total    = sum(dist.values())
                pcts     = {cat: count / total * 100 for cat, count in dist.items()}
                max_pct  = max(pcts.values())
                min_pct  = min(pcts.values())
                imbalance_ratio = max_pct / min_pct if min_pct > 0 else float("inf")

                col_lower = col.lower()
                is_label  = any(k in col_lower for k in ["label", "class", "target", "y", "diagnosis", "category", "outcome"])

                if is_label and imbalance_ratio > 5:
                    severity = 3 if imbalance_ratio > 20 else 2
                    dominant = max(pcts, key=pcts.get)
                    minority = min(pcts, key=pcts.get)
                    all_findings.append({
                        "category": f"CLASS IMBALANCE — '{col}'",
                        "severity": severity,
                        "items": [
                            f"Imbalance ratio: {imbalance_ratio:.1f}:1",
                            f"Dominant class '{dominant}': {pcts[dominant]:.1f}%",
                            f"Minority class '{minority}': {pcts[minority]:.1f}%",
                            "⚠ Severe imbalance may bias model training" if severity == 3 else "ℹ Consider balancing techniques"
                        ]
                    })

            # High cardinality warning
            if n_cats > n * 0.5 and n_cats > 100:
                all_findings.append({
                    "category": f"HIGH CARDINALITY — '{col}'",
                    "severity": 1,
                    "items": [
                        f"{n_cats} unique values in {n} rows ({n_cats/n*100:.1f}% cardinality)",
                        "Possibly an ID or free-text column — may not be useful for training"
                    ]
                })

    # ── Sort and display ───────────────────────────────────────
    all_findings.sort(key=lambda x: x["severity"], reverse=True)

    if not all_findings:
        lines.append("  ✓ No anomalies detected")
        lines.append(f"  Dataset appears clean ({n} rows, {len(headers)} columns)")
    else:
        for finding in all_findings:
            sev_label = {3: "HIGH  ", 2: "MEDIUM", 1: "LOW   "}.get(finding["severity"], "INFO  ")
            lines.append(f"  [{sev_label}] {finding['category']}")
            for item in finding["items"]:
                lines.append(f"    {item}")
            lines.append("")

    # Summary
    high   = sum(1 for f in all_findings if f["severity"] == 3)
    medium = sum(1 for f in all_findings if f["severity"] == 2)
    low    = sum(1 for f in all_findings if f["severity"] == 1)

    lines.append("─" * 60)
    if not all_findings:
        lines.append("  ✓ CLEAN — dataset passed all checks")
    else:
        if high:   lines.append(f"  ✗ {high} HIGH severity issue(s) — address before training")
        if medium: lines.append(f"  ⚠ {medium} MEDIUM severity issue(s) — review recommended")
        if low:    lines.append(f"  ℹ {low} LOW severity issue(s) — informational")

    return True, "\n".join(lines)


def _detect_type(values):
    if not values:
        return "categorical"
    numeric_count = sum(1 for v in values[:50] if _is_numeric(v))
    return "numeric" if numeric_count / max(len(values[:50]), 1) > 0.8 else "categorical"


def _is_numeric(v):
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False


def _read_csv(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except Exception:
        return []