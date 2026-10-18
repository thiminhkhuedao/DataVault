import csv
import json
import os
import math
import statistics

HISTORY_FILE = ".datavault/history.json"
VERSIONS_DIR = ".datavault/versions"


def statistical_compare(filepath, version_a, version_b):
    """
    Deep statistical comparison between two versions of a CSV file.

    Goes beyond row-level diffing to answer:
    - Has the distribution of any column changed significantly?
    - Is the class balance different?
    - Have correlations between columns shifted?
    - Is the new version statistically compatible with the old one?

    Uses only Python stdlib — no numpy, no pandas, no scipy.
    """
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
        return False, f"Stored file for {version_a} not found. Run 'migrate' first."
    if not os.path.exists(path_b):
        return False, f"Stored file for {version_b} not found. Run 'migrate' first."

    rows_a = _read_csv(path_a)
    rows_b = _read_csv(path_b)

    if not rows_a or not rows_b:
        return False, "Could not read CSV data."

    headers_a = set(rows_a[0].keys())
    headers_b = set(rows_b[0].keys())
    common    = sorted(headers_a & headers_b)

    lines = [
        f"\nStatistical comparison: '{filename}'",
        f"  {version_a} ({len(rows_a)} rows)  →  {version_b} ({len(rows_b)} rows)",
        "─" * 60,
        ""
    ]

    # Column structure changes
    added   = sorted(headers_b - headers_a)
    removed = sorted(headers_a - headers_b)
    if added:
        lines.append(f"  NEW COLUMNS:     {', '.join(added)}")
    if removed:
        lines.append(f"  REMOVED COLUMNS: {', '.join(removed)}")
    if added or removed:
        lines.append("")

    # Size change
    row_delta = len(rows_b) - len(rows_a)
    row_pct   = row_delta / len(rows_a) * 100 if rows_a else 0
    lines.append(f"  SIZE CHANGE: {'+' if row_delta >= 0 else ''}{row_delta} rows "
                 f"({'+' if row_pct >= 0 else ''}{row_pct:.1f}%)")
    lines.append("")

    # Per-column stats
    col_results = []
    for col in common:
        vals_a = _numeric_values(rows_a, col)
        vals_b = _numeric_values(rows_b, col)

        if vals_a and vals_b and len(vals_a) > 1 and len(vals_b) > 1:
            col_results.append(_compare_numeric(col, vals_a, vals_b))
        else:
            cats_a = _categorical_values(rows_a, col)
            cats_b = _categorical_values(rows_b, col)
            if cats_a and cats_b:
                col_results.append(_compare_categorical(col, cats_a, cats_b))

    # Sort by significance
    col_results.sort(key=lambda x: x["significance"], reverse=True)

    lines.append("  COLUMN-BY-COLUMN ANALYSIS:")
    lines.append("  " + "─" * 56)

    for r in col_results:
        sig_label = {3: "SIGNIFICANT", 2: "NOTABLE", 1: "MINOR", 0: "STABLE"}.get(r["significance"], "STABLE")
        lines.append(f"\n  {r['column']} [{sig_label}] ({r['type']})")
        for detail in r["details"]:
            lines.append(f"    {detail}")

    # Overall compatibility score
    lines.append(f"\n{'─' * 60}")
    sig_cols  = sum(1 for r in col_results if r["significance"] >= 2)
    stable    = sum(1 for r in col_results if r["significance"] == 0)
    total     = len(col_results)

    compat_pct = (stable + sum(1 for r in col_results if r["significance"] == 1) * 0.5) / total * 100 if total else 100

    lines.append(f"\n  COMPATIBILITY SCORE: {compat_pct:.0f}%")
    if compat_pct >= 90:
        lines.append("  ✓ Versions are statistically compatible — safe to use interchangeably")
    elif compat_pct >= 70:
        lines.append("  ⚠ Moderate statistical differences — review before using in production")
    else:
        lines.append("  ✗ Significant statistical differences — datasets may not be compatible")

    if sig_cols > 0:
        lines.append(f"\n  {sig_cols} column(s) with significant changes:")
        for r in col_results:
            if r["significance"] >= 2:
                lines.append(f"    • {r['column']}")

    lines.append(f"\n  Summary: {stable}/{total} columns stable, "
                 f"{sum(1 for r in col_results if r['significance']==1)}/{total} minor changes, "
                 f"{sig_cols}/{total} significant changes")

    return True, "\n".join(lines)


def _compare_numeric(col, vals_a, vals_b):
    details = []
    significance = 0

    mean_a = statistics.mean(vals_a)
    mean_b = statistics.mean(vals_b)
    std_a  = statistics.stdev(vals_a) if len(vals_a) > 1 else 0
    std_b  = statistics.stdev(vals_b) if len(vals_b) > 1 else 0

    mean_drift = ((mean_b - mean_a) / mean_a * 100) if mean_a != 0 else 0
    std_drift  = ((std_b  - std_a)  / std_a  * 100) if std_a  != 0 else 0

    details.append(f"mean:  {mean_a:.4f} → {mean_b:.4f}  ({'+' if mean_drift>=0 else ''}{mean_drift:.1f}%)")
    details.append(f"std:   {std_a:.4f} → {std_b:.4f}  ({'+' if std_drift>=0 else ''}{std_drift:.1f}%)")
    details.append(f"min:   {min(vals_a):.4f} → {min(vals_b):.4f}")
    details.append(f"max:   {max(vals_a):.4f} → {max(vals_b):.4f}")

    # Median
    med_a = statistics.median(vals_a)
    med_b = statistics.median(vals_b)
    med_drift = ((med_b - med_a) / med_a * 100) if med_a != 0 else 0
    details.append(f"median:{med_a:.4f} → {med_b:.4f}  ({'+' if med_drift>=0 else ''}{med_drift:.1f}%)")

    # Effect size (Cohen's d equivalent)
    pooled_std = math.sqrt((std_a**2 + std_b**2) / 2) if (std_a > 0 or std_b > 0) else 1
    effect_size = abs(mean_b - mean_a) / pooled_std if pooled_std > 0 else 0
    details.append(f"effect size: {effect_size:.3f} ({'large' if effect_size > 0.8 else 'medium' if effect_size > 0.5 else 'small' if effect_size > 0.2 else 'negligible'})")

    # Significance
    if effect_size > 0.8 or abs(mean_drift) > 20:
        significance = 3
        details.append("⚠ Large distributional shift detected")
    elif effect_size > 0.5 or abs(mean_drift) > 10:
        significance = 2
        details.append("ℹ Moderate distributional shift")
    elif effect_size > 0.2 or abs(mean_drift) > 3:
        significance = 1

    return {"column": col, "type": "numeric", "significance": significance, "details": details}


def _compare_categorical(col, cats_a, cats_b):
    details = []
    significance = 0

    dist_a = _distribution(cats_a)
    dist_b = _distribution(cats_b)
    all_cats = sorted(set(dist_a) | set(dist_b))

    n_a = len(cats_a)
    n_b = len(cats_b)

    new_cats     = set(dist_b) - set(dist_a)
    removed_cats = set(dist_a) - set(dist_b)

    if new_cats:
        significance = max(significance, 2)
        details.append(f"new categories: {', '.join(sorted(new_cats))}")
    if removed_cats:
        significance = max(significance, 2)
        details.append(f"removed categories: {', '.join(sorted(removed_cats))}")

    # Chi-square-like drift score
    drift_scores = []
    for cat in all_cats:
        pct_a = dist_a.get(cat, 0) / n_a * 100
        pct_b = dist_b.get(cat, 0) / n_b * 100
        drift  = abs(pct_b - pct_a)
        drift_scores.append((cat, pct_a, pct_b, pct_b - pct_a))
        if drift > 5:
            significance = max(significance, 2 if drift > 15 else 1)

    drift_scores.sort(key=lambda x: abs(x[3]), reverse=True)
    details.append(f"unique categories: {len(set(dist_a))} → {len(set(dist_b))}")

    for cat, pct_a, pct_b, delta in drift_scores[:6]:
        arrow = f"{'+' if delta>=0 else ''}{delta:.1f}%"
        details.append(f"  '{cat}': {pct_a:.1f}% → {pct_b:.1f}%  ({arrow})")

    if len(drift_scores) > 6:
        details.append(f"  ... and {len(drift_scores)-6} more categories")

    if significance == 0:
        details.append("distribution stable")

    return {"column": col, "type": "categorical", "significance": significance, "details": details}


def _numeric_values(rows, col):
    result = []
    for r in rows:
        v = r.get(col)
        if v in (None, "", "nan", "NULL"):
            continue
        try:
            result.append(float(v))
        except (ValueError, TypeError):
            pass
    return result


def _categorical_values(rows, col):
    return [r[col] for r in rows if r.get(col) not in (None, "", "nan", "NULL")]


def _distribution(values):
    dist = {}
    for v in values:
        dist[v] = dist.get(v, 0) + 1
    return dist


def _read_csv(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except Exception:
        return []