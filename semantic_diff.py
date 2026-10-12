import csv
import json
import os
import math
import statistics

HISTORY_FILE = ".datavault/history.json"
VERSIONS_DIR = ".datavault/versions"


def semantic_diff(filepath, version_a, version_b):
    filename = os.path.basename(filepath)

    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions = history["files"][filename]["versions"]
    va = next((v for v in versions if v["version_id"] == version_a), None)
    vb = next((v for v in versions if v["version_id"] == version_b), None)

    if not va:
        return False, f"Version '{version_a}' not found."
    if not vb:
        return False, f"Version '{version_b}' not found."

    safe_name = filename.replace("/", "_").replace("\\", "_")
    path_a = os.path.join(VERSIONS_DIR, f"{safe_name}__{version_a}")
    path_b = os.path.join(VERSIONS_DIR, f"{safe_name}__{version_b}")

    if not os.path.exists(path_a):
        return False, f"Stored file for {version_a} not found."
    if not os.path.exists(path_b):
        return False, f"Stored file for {version_b} not found."

    rows_a = _read_csv(path_a)
    rows_b = _read_csv(path_b)

    if not rows_a or not rows_b:
        return False, "Could not read CSV data. Only CSV files are supported."

    headers_a = set(rows_a[0].keys())
    headers_b = set(rows_b[0].keys())
    all_headers = headers_a | headers_b

    lines = [
        f"\nSemantic diff: '{filename}'  {version_a} → {version_b}",
        "─" * 60,
        f"  Rows:     {len(rows_a)} → {len(rows_b)} "
        f"({'+'if len(rows_b)>len(rows_a) else ''}{len(rows_b)-len(rows_a)})",
        f"  Columns:  {len(headers_a)} → {len(headers_b)}",
        ""
    ]

    # Added / removed columns
    added_cols   = headers_b - headers_a
    removed_cols = headers_a - headers_b
    if added_cols:
        lines.append(f"  NEW COLUMNS:     {', '.join(sorted(added_cols))}")
    if removed_cols:
        lines.append(f"  REMOVED COLUMNS: {', '.join(sorted(removed_cols))}")
    if added_cols or removed_cols:
        lines.append("")

    # Per-column analysis
    common_cols = sorted(headers_a & headers_b)
    findings = []

    for col in common_cols:
        vals_a = [r[col] for r in rows_a if r.get(col) not in (None, "", "nan")]
        vals_b = [r[col] for r in rows_b if r.get(col) not in (None, "", "nan")]

        missing_a = len(rows_a) - len(vals_a)
        missing_b = len(rows_b) - len(vals_b)

        col_type = _detect_type(vals_a + vals_b)

        if col_type == "numeric":
            findings.append(_analyze_numeric(col, vals_a, vals_b, missing_a, missing_b, len(rows_a), len(rows_b)))
        else:
            findings.append(_analyze_categorical(col, vals_a, vals_b, missing_a, missing_b, len(rows_a), len(rows_b)))

    # Sort by severity
    findings.sort(key=lambda x: x["severity"], reverse=True)

    for f in findings:
        if f["severity"] == 0 and len(findings) > 5:
            continue
        lines.append(f"  [{_severity_label(f['severity'])}] {f['column']}")
        for detail in f["details"]:
            lines.append(f"    {detail}")
        lines.append("")

    # Summary
    high   = sum(1 for f in findings if f["severity"] >= 3)
    medium = sum(1 for f in findings if f["severity"] == 2)
    low    = sum(1 for f in findings if f["severity"] == 1)
    none   = sum(1 for f in findings if f["severity"] == 0)

    lines.append("─" * 60)
    lines.append(f"  {len(common_cols)} columns analyzed")
    if high:   lines.append(f"  ✗ {high} HIGH severity change(s)")
    if medium: lines.append(f"  ⚠ {medium} MEDIUM severity change(s)")
    if low:    lines.append(f"  ℹ {low} LOW severity change(s)")
    if none:   lines.append(f"  ✓ {none} column(s) unchanged")

    return True, "\n".join(lines)


def _analyze_numeric(col, vals_a, vals_b, missing_a, missing_b, total_a, total_b):
    details  = []
    severity = 0

    try:
        nums_a = [float(v) for v in vals_a]
        nums_b = [float(v) for v in vals_b]
    except ValueError:
        return _analyze_categorical(col, vals_a, vals_b, missing_a, missing_b, total_a, total_b)

    if not nums_a or not nums_b:
        return {"column": col, "severity": 1, "details": ["No numeric data available"]}

    mean_a = statistics.mean(nums_a)
    mean_b = statistics.mean(nums_b)
    mean_delta = ((mean_b - mean_a) / mean_a * 100) if mean_a != 0 else 0

    std_a = statistics.stdev(nums_a) if len(nums_a) > 1 else 0
    std_b = statistics.stdev(nums_b) if len(nums_b) > 1 else 0

    min_a, max_a = min(nums_a), max(nums_a)
    min_b, max_b = min(nums_b), max(nums_b)

    details.append(f"mean:  {mean_a:.3f} → {mean_b:.3f}  ({'+' if mean_delta >= 0 else ''}{mean_delta:.1f}% drift)")
    details.append(f"std:   {std_a:.3f} → {std_b:.3f}")
    details.append(f"range: [{min_a:.2f}, {max_a:.2f}] → [{min_b:.2f}, {max_b:.2f}]")

    # Missing values
    if missing_a != missing_b:
        pct_a = missing_a / total_a * 100
        pct_b = missing_b / total_b * 100
        details.append(f"missing: {missing_a} ({pct_a:.1f}%) → {missing_b} ({pct_b:.1f}%)")
        if pct_b > pct_a + 5:
            severity = max(severity, 2)

    # Severity based on mean drift
    abs_drift = abs(mean_delta)
    if abs_drift > 20:
        severity = max(severity, 3)
        details.append(f"⚠ Large mean drift ({abs_drift:.1f}%) — possible data shift or normalization change")
    elif abs_drift > 10:
        severity = max(severity, 2)
        details.append(f"ℹ Moderate mean drift ({abs_drift:.1f}%)")
    elif abs_drift > 3:
        severity = max(severity, 1)

    # New min/max outside previous range
    if min_b < min_a or max_b > max_a:
        severity = max(severity, 2)
        details.append("⚠ New values outside previous range — potential outliers introduced")

    return {"column": col, "severity": severity, "details": details}


def _analyze_categorical(col, vals_a, vals_b, missing_a, missing_b, total_a, total_b):
    details  = []
    severity = 0

    if not vals_a and not vals_b:
        return {"column": col, "severity": 0, "details": ["Empty column"]}

    dist_a = _distribution(vals_a)
    dist_b = _distribution(vals_b)

    all_cats = set(dist_a) | set(dist_b)
    new_cats = set(dist_b) - set(dist_a)
    removed_cats = set(dist_a) - set(dist_b)

    n_a = len(vals_a)
    n_b = len(vals_b)

    if new_cats:
        severity = max(severity, 2)
        details.append(f"NEW categories: {', '.join(sorted(new_cats))}")

    if removed_cats:
        severity = max(severity, 2)
        details.append(f"REMOVED categories: {', '.join(sorted(removed_cats))}")

    # Distribution drift per category
    drifts = []
    for cat in sorted(all_cats):
        pct_a = dist_a.get(cat, 0) / n_a * 100 if n_a > 0 else 0
        pct_b = dist_b.get(cat, 0) / n_b * 100 if n_b > 0 else 0
        delta  = pct_b - pct_a
        if abs(delta) >= 2:
            drifts.append((cat, pct_a, pct_b, delta))

    if drifts:
        # Sort by absolute drift
        drifts.sort(key=lambda x: abs(x[3]), reverse=True)
        for cat, pct_a, pct_b, delta in drifts[:5]:
            details.append(f"'{cat}': {pct_a:.1f}% → {pct_b:.1f}%  ({'+' if delta>=0 else ''}{delta:.1f}%)")
            if abs(delta) > 10:
                severity = max(severity, 3)
                details.append(f"  ⚠ Large distribution shift — potential relabeling or class imbalance change")
            elif abs(delta) > 5:
                severity = max(severity, 2)
        if len(drifts) > 5:
            details.append(f"  ... and {len(drifts)-5} more categories with drift")

    # Missing values
    if missing_a != missing_b:
        pct_a = missing_a / total_a * 100
        pct_b = missing_b / total_b * 100
        details.append(f"missing: {missing_a} ({pct_a:.1f}%) → {missing_b} ({pct_b:.1f}%)")
        if pct_b > pct_a + 5:
            severity = max(severity, 2)

    if not details:
        details.append("No significant changes detected")

    return {"column": col, "severity": severity, "details": details}


def _detect_type(values):
    if not values:
        return "categorical"
    numeric_count = 0
    for v in values[:50]:
        try:
            float(v)
            numeric_count += 1
        except (ValueError, TypeError):
            pass
    return "numeric" if numeric_count / max(len(values[:50]), 1) > 0.8 else "categorical"


def _distribution(values):
    dist = {}
    for v in values:
        dist[v] = dist.get(v, 0) + 1
    return dist


def _severity_label(s):
    if s >= 3: return "HIGH  "
    if s == 2: return "MEDIUM"
    if s == 1: return "LOW   "
    return "OK    "


def _read_csv(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except Exception:
        return []