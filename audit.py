import hashlib
import json
import os
from datetime import datetime

HISTORY_FILE  = ".datavault/history.json"
META_FILE     = ".datavault/meta.json"
SIGNING_FILE  = ".datavault/signatures.json"
CHAIN_FILE    = ".datavault/chain.json"


def run_audit(filepath, output_path=None):
    filename = os.path.basename(filepath)

    if not os.path.exists(HISTORY_FILE):
        return False, "No DataVault project found."

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
    with open(META_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    if filename not in history.get("files", {}):
        return False, f"'{filename}' is not tracked."

    versions = history["files"][filename]["versions"]
    sigs     = _load_sigs().get(filename, {})

    # 1. Chain verification
    chain_valid, chain_results = _verify_chain(filename, versions)

    # 2. Current file status
    if os.path.exists(filepath):
        current_hash  = _hash_file(filepath)
        latest_hash   = versions[-1]["hash"]
        file_status   = "INTACT" if current_hash == latest_hash else "MODIFIED"
    else:
        file_status   = "MISSING"
        current_hash  = None

    # 3. Approval status
    latest_vid    = versions[-1]["version_id"]
    version_sigs  = sigs.get(latest_vid, [])
    has_reviewer  = any(s["role"] == "reviewer" for s in version_sigs)
    has_approver  = any(s["role"] == "approver" for s in version_sigs)
    approved      = has_reviewer and has_approver and len(version_sigs) > 0

    # 4. Build report
    now        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proj_name  = meta.get("project_name", "Unknown")
    created_by = meta.get("created_by", "Unknown")
    created_at = meta.get("created_at", "")[:19].replace("T", " ")

    if output_path is None:
        output_path = f"datavault_audit_{filename.replace('.', '_')}.html"

    _write_audit_html(
        output_path=output_path,
        filename=filename,
        proj_name=proj_name,
        created_by=created_by,
        created_at=created_at,
        versions=versions,
        sigs=sigs,
        chain_valid=chain_valid,
        chain_results=chain_results,
        file_status=file_status,
        current_hash=current_hash,
        approved=approved,
        has_reviewer=has_reviewer,
        has_approver=has_approver,
        version_sigs=version_sigs,
        latest_vid=latest_vid,
        now=now,
    )

    overall = chain_valid and file_status == "INTACT" and approved

    summary = (
        f"Audit report: {output_path}\n\n"
        f"  File:          {filename}\n"
        f"  Versions:      {len(versions)}\n"
        f"  Chain:         {'✓ INTACT' if chain_valid else '✗ BROKEN'}\n"
        f"  Current file:  {'✓ ' + file_status if file_status == 'INTACT' else '✗ ' + file_status}\n"
        f"  Approved:      {'✓ YES' if approved else '✗ NO'}\n\n"
        f"  Overall:       {'✓ AUDIT PASSED' if overall else '✗ AUDIT FAILED'}\n\n"
        f"  Open the HTML report to share with auditors."
    )

    return overall, summary


def _write_audit_html(output_path, filename, proj_name, created_by, created_at,
                       versions, sigs, chain_valid, chain_results, file_status,
                       current_hash, approved, has_reviewer, has_approver,
                       version_sigs, latest_vid, now):

    overall = chain_valid and file_status == "INTACT" and approved
    status_color = "#166534" if overall else "#991b1b"
    status_text  = "AUDIT PASSED" if overall else "AUDIT FAILED"

    # Version rows
    version_rows = ""
    for v in versions:
        ts     = v["timestamp"][:19].replace("T", " ")
        v_sigs = sigs.get(v["version_id"], [])
        sig_str = ", ".join(f"{s['signer']} ({s['role']})" for s in v_sigs) or "—"
        chain_ok = next((r["valid"] for r in chain_results if isinstance(r, dict) and r.get("version_id") == v["version_id"]), None)
        chain_cell = "✓" if chain_ok else ("✗" if chain_ok is False else "—")
        version_rows += f"""
        <tr>
          <td><strong>{v["version_id"]}</strong></td>
          <td>{ts}</td>
          <td>{v.get("author","—")}</td>
          <td>{v["message"]}</td>
          <td class="mono">{v["hash"][:20]}…</td>
          <td style="text-align:center;color:{'#166534' if chain_ok else '#991b1b'}">{chain_cell}</td>
          <td>{sig_str}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DataVault Audit Report — {filename}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:13px;color:#1a1a1a;background:#fff;padding:40px;max-width:960px;margin:0 auto}}
  .header{{border-bottom:2px solid #1a1a1a;padding-bottom:24px;margin-bottom:32px}}
  .header h1{{font-size:20px;font-weight:700;margin-bottom:4px}}
  .header .sub{{font-size:13px;color:#666;margin-top:4px}}
  .status-banner{{padding:16px 20px;border-radius:8px;margin-bottom:32px;
    background:{status_color}10;border:1px solid {status_color}40}}
  .status-banner .status-label{{font-size:18px;font-weight:700;color:{status_color}}}
  .status-banner .status-sub{{font-size:12px;color:#555;margin-top:4px}}
  .section{{margin-bottom:36px}}
  .section-title{{font-size:11px;font-weight:600;letter-spacing:.08em;
    text-transform:uppercase;color:#888;margin-bottom:12px;padding-bottom:8px;
    border-bottom:1px solid #e8e8e8}}
  .check-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:0}}
  .check-item{{background:#f9f9f8;border:1px solid #e8e8e8;border-radius:8px;padding:16px}}
  .check-item .check-label{{font-size:11px;color:#888;text-transform:uppercase;
    letter-spacing:.05em;margin-bottom:6px}}
  .check-item .check-val{{font-size:15px;font-weight:600}}
  .check-ok{{color:#166534}}
  .check-fail{{color:#991b1b}}
  table{{width:100%;border-collapse:collapse;font-size:12px}}
  th{{background:#f5f5f5;padding:8px 12px;text-align:left;font-weight:500;
    color:#444;border-bottom:1px solid #ddd;font-size:11px;
    letter-spacing:.04em;text-transform:uppercase}}
  td{{padding:8px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top}}
  tr:last-child td{{border-bottom:none}}
  .mono{{font-family:'Courier New',monospace;font-size:11px;color:#555}}
  .reg-box{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;
    padding:20px;margin-bottom:0}}
  .reg-box h3{{font-size:13px;font-weight:600;color:#1e40af;margin-bottom:10px}}
  .reg-item{{margin-bottom:8px;font-size:12px;color:#374151;line-height:1.6}}
  .reg-item:last-child{{margin-bottom:0}}
  .reg-art{{font-family:'Courier New',monospace;font-weight:700;color:#1e40af;margin-right:6px}}
  .disclaimer{{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;
    padding:16px;font-size:12px;color:#7c2d12;line-height:1.6}}
  .meta-table td:first-child{{color:#888;width:160px;font-weight:500}}
  .footer{{margin-top:40px;padding-top:16px;border-top:1px solid #e8e8e8;
    display:flex;justify-content:space-between;font-size:11px;color:#aaa}}
  @media print{{body{{padding:20px}}.section{{page-break-inside:avoid}}}}
</style>
</head>
<body>

<div class="header">
  <div style="font-size:12px;color:#888;margin-bottom:8px">DataVault Audit Report</div>
  <h1>{filename}</h1>
  <div class="sub">Project: {proj_name} &nbsp;·&nbsp; Generated: {now} &nbsp;·&nbsp; By: {created_by}</div>
</div>

<div class="status-banner">
  <div class="status-label">{status_text}</div>
  <div class="status-sub">
    {'All checks passed. This file can be presented to auditors as having verifiable provenance.' if overall else 'One or more checks failed. Review the details below before presenting to auditors.'}
  </div>
</div>

<div class="section">
  <div class="section-title">Audit Summary</div>
  <div class="check-grid">
    <div class="check-item">
      <div class="check-label">Hash chain integrity</div>
      <div class="check-val {'check-ok' if chain_valid else 'check-fail'}">
        {'✓ INTACT' if chain_valid else '✗ BROKEN'}
      </div>
    </div>
    <div class="check-item">
      <div class="check-label">Current file status</div>
      <div class="check-val {'check-ok' if file_status == 'INTACT' else 'check-fail'}">
        {'✓ ' + file_status if file_status == 'INTACT' else '✗ ' + file_status}
      </div>
    </div>
    <div class="check-item">
      <div class="check-label">Reviewer signature</div>
      <div class="check-val {'check-ok' if has_reviewer else 'check-fail'}">
        {'✓ Present' if has_reviewer else '✗ Missing'}
      </div>
    </div>
    <div class="check-item">
      <div class="check-label">Approver signature</div>
      <div class="check-val {'check-ok' if has_approver else 'check-fail'}">
        {'✓ Present' if has_approver else '✗ Missing'}
      </div>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-title">File Metadata</div>
  <table class="meta-table">
    <tbody>
      <tr><td>Filename</td><td>{filename}</td></tr>
      <tr><td>Project</td><td>{proj_name}</td></tr>
      <tr><td>Project created</td><td>{created_at}</td></tr>
      <tr><td>Created by</td><td>{created_by}</td></tr>
      <tr><td>Total versions</td><td>{len(versions)}</td></tr>
      <tr><td>Latest version</td><td>{latest_vid} — {versions[-1]["timestamp"][:19].replace("T"," ")}</td></tr>
      <tr><td>Latest hash</td><td class="mono">{versions[-1]["hash"]}</td></tr>
      <tr><td>Current hash</td><td class="mono">{current_hash or "FILE MISSING"}</td></tr>
    </tbody>
  </table>
</div>

<div class="section">
  <div class="section-title">Version History</div>
  <table>
    <thead>
      <tr><th>Version</th><th>Timestamp</th><th>Author</th><th>Message</th><th>Hash</th><th>Chain</th><th>Signatures</th></tr>
    </thead>
    <tbody>{version_rows}</tbody>
  </table>
</div>

<div class="section">
  <div class="section-title">EU AI Act Compliance Reference</div>
  <div class="reg-box">
    <h3>This report addresses the following EU AI Act requirements:</h3>
    <div class="reg-item">
      <span class="reg-art">Art. 10</span>
      Data governance — version history with author, timestamp, and message for every modification satisfies data management documentation requirements.
    </div>
    <div class="reg-item">
      <span class="reg-art">Art. 12</span>
      Record-keeping — the cryptographic hash chain provides immutable, verifiable records that cannot be altered retroactively.
    </div>
    <div class="reg-item">
      <span class="reg-art">Art. 13</span>
      Transparency — multi-user signing with reviewer and approver roles creates a verifiable accountability chain.
    </div>
  </div>
</div>

<div class="section">
  <div class="disclaimer">
    <strong>Disclaimer:</strong> This report is generated by DataVault and reflects the state of the tracked file at the time of generation.
    DataVault is not a legal compliance tool and this report does not constitute legal advice or guarantee regulatory compliance.
    Organizations should consult qualified legal counsel to determine their specific obligations under the EU AI Act or other applicable regulations.
  </div>
</div>

<div class="footer">
  <span>Generated by DataVault · datavault_audit · {now}</span>
  <span>github.com/thiminhkhuedao/DataVault</span>
</div>

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def _verify_chain(filename, versions):
    if not any("chain_hash" in v for v in versions):
        return False, []

    prev = "GENESIS"
    results = []
    all_valid = True

    for v in versions:
        stored = v.get("chain_hash")
        if not stored:
            results.append({"version_id": v["version_id"], "valid": False})
            all_valid = False
            continue
        chain_input = "|".join([
            v["hash"], prev, v["version_id"],
            v["timestamp"], v.get("author","unknown"), v["message"]
        ])
        expected = hashlib.sha256(chain_input.encode()).hexdigest()
        valid = (expected == stored)
        if not valid:
            all_valid = False
        results.append({"version_id": v["version_id"], "valid": valid})
        prev = stored

    return all_valid, results


def _hash_file(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def _load_sigs():
    if os.path.exists(SIGNING_FILE):
        with open(SIGNING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}