# ============================================================
# dashboard.py — web dashboard for DataVault
#
# Usage:
#   python dashboard.py
#   Then open: http://localhost:5000
#
# ============================================================

import http.server
import json
import os
import sys
import webbrowser
import threading
import hashlib
from datetime import datetime

VAULT_DIR    = ".datavault"
HISTORY_FILE = ".datavault/history.json"
META_FILE    = ".datavault/meta.json"
PORT         = 5000

# ── HTML for the dashboard ───────────────────────────────────

def build_dashboard_html():

    if not os.path.exists(HISTORY_FILE):
        return _error_page("No DataVault project found. Run 'python datavault.py init <name>' first.")

    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)
    with open(META_FILE, "r") as f:
        meta = json.load(f)

    proj_name  = meta.get("project_name", "DataVault Project")
    created_by = meta.get("created_by", "unknown")

    # Build file cards
    file_cards = ""
    for filename, data in history["files"].items():
        versions = data["versions"]
        latest   = versions[-1]

        # Check current file status
        if os.path.exists(filename):
            curr_hash = _hash_file(filename)
            if curr_hash == latest["hash"]:
                status_html = '<span class="status ok">✓ up to date</span>'
            else:
                status_html = '<span class="status warn">⚠ modified — run commit</span>'
        else:
            status_html = '<span class="status err">✗ file missing</span>'

        # Build version timeline
        timeline_items = ""
        for i, v in enumerate(reversed(versions)):
            ts       = v["timestamp"][:19].replace("T", " ")
            tags     = v.get("tags", [])
            tag_html = "".join(f'<span class="tag">{t["message"]}</span>' for t in tags)
            is_latest = (i == 0)

            timeline_items += f"""
            <div class="version-item {'latest' if is_latest else ''}">
              <div class="version-dot"></div>
              <div class="version-body">
                <div class="version-top">
                  <span class="vid">{v["version_id"]}</span>
                  <span class="vmsg">{v["message"]}</span>
                  {'<span class="latest-badge">latest</span>' if is_latest else ''}
                </div>
                <div class="version-meta">
                  {ts} · {v.get("author","?")} · {_fmt_size(v["size_bytes"])}
                </div>
                <div class="version-hash">{v["hash"][:32]}…</div>
                {f'<div class="tags">{tag_html}</div>' if tags else ''}
              </div>
            </div>"""

        file_cards += f"""
        <div class="file-card">
          <div class="file-card-header">
            <div>
              <div class="filename">{filename}</div>
              <div class="file-meta">{len(versions)} version(s) · last: {latest["timestamp"][:10]}</div>
            </div>
            {status_html}
          </div>
          <div class="timeline">{timeline_items}</div>
        </div>"""

    if not file_cards:
        file_cards = '<div class="empty">No files tracked yet. Use <code>datavault add &lt;file&gt; "&lt;message&gt;"</code> to start.</div>'

    total_versions = sum(len(d["versions"]) for d in history["files"].values())

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DataVault — {proj_name}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f7f7f5; color: #1a1a1a; min-height: 100vh; }}

  .topbar {{ background: #1a1a1a; color: #fff; padding: 0 32px;
             height: 56px; display: flex; align-items: center;
             justify-content: space-between; position: sticky; top: 0; z-index: 10; }}
  .topbar-left {{ display: flex; align-items: center; gap: 12px; }}
  .logo {{ font-size: 15px; font-weight: 600; letter-spacing: -0.3px; }}
  .proj {{ font-size: 13px; color: #999; }}
  .topbar-right {{ font-size: 12px; color: #666; }}

  .stats-bar {{ background: #fff; border-bottom: 1px solid #e8e8e8;
                padding: 16px 32px; display: flex; gap: 32px; }}
  .stat {{ display: flex; flex-direction: column; gap: 2px; }}
  .stat-val {{ font-size: 20px; font-weight: 600; color: #1a1a1a; }}
  .stat-lbl {{ font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }}

  .main {{ max-width: 860px; margin: 32px auto; padding: 0 24px; }}
  .section-title {{ font-size: 13px; font-weight: 500; color: #888;
                    text-transform: uppercase; letter-spacing: 0.5px;
                    margin-bottom: 16px; }}

  .file-card {{ background: #fff; border: 1px solid #e8e8e8; border-radius: 10px;
                margin-bottom: 20px; overflow: hidden; }}
  .file-card-header {{ padding: 16px 20px; border-bottom: 1px solid #f0f0f0;
                       display: flex; justify-content: space-between; align-items: flex-start; }}
  .filename {{ font-size: 15px; font-weight: 600; margin-bottom: 3px; }}
  .file-meta {{ font-size: 12px; color: #888; }}

  .status {{ font-size: 12px; padding: 4px 10px; border-radius: 20px; font-weight: 500; }}
  .status.ok   {{ background: #e8f4e8; color: #2a6a2a; }}
  .status.warn {{ background: #fff3e0; color: #8a4a00; }}
  .status.err  {{ background: #fdecea; color: #8a1a1a; }}

  .timeline {{ padding: 12px 20px 4px; }}
  .version-item {{ display: flex; gap: 12px; padding: 10px 0;
                   border-bottom: 1px solid #f5f5f5; position: relative; }}
  .version-item:last-child {{ border-bottom: none; }}
  .version-dot {{ width: 10px; height: 10px; border-radius: 50%;
                  background: #d0d0d0; margin-top: 5px; flex-shrink: 0; }}
  .version-item.latest .version-dot {{ background: #2a6a2a; }}
  .version-body {{ flex: 1; min-width: 0; }}
  .version-top {{ display: flex; align-items: center; gap: 8px; margin-bottom: 3px; flex-wrap: wrap; }}
  .vid {{ font-family: 'Courier New', monospace; font-size: 12px; font-weight: 700;
          background: #f0f0f0; padding: 1px 6px; border-radius: 4px; color: #444; }}
  .vmsg {{ font-size: 13px; color: #1a1a1a; }}
  .latest-badge {{ font-size: 10px; background: #e8f4e8; color: #2a6a2a;
                   padding: 2px 7px; border-radius: 10px; font-weight: 500; }}
  .version-meta {{ font-size: 11px; color: #999; margin-bottom: 3px; }}
  .version-hash {{ font-family: 'Courier New', monospace; font-size: 10px; color: #bbb; }}
  .tags {{ margin-top: 5px; }}
  .tag {{ display: inline-block; background: #e8f0fe; color: #1a56a8;
          padding: 2px 8px; border-radius: 10px; font-size: 11px;
          margin: 2px 3px 2px 0; border: 1px solid #c2d4f5; }}

  .empty {{ padding: 32px; text-align: center; color: #999; font-size: 14px; }}
  .empty code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-size: 13px; color: #444; }}

  .commands {{ background: #1a1a1a; border-radius: 10px; padding: 20px 24px; margin-top: 32px; }}
  .commands-title {{ color: #888; font-size: 11px; text-transform: uppercase;
                     letter-spacing: 0.5px; margin-bottom: 12px; }}
  .cmd-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }}
  .cmd {{ font-family: 'Courier New', monospace; font-size: 12px; color: #ccc;
          padding: 4px 0; }}
  .cmd span {{ color: #7dd3a8; }}

  .refresh-note {{ text-align: center; color: #aaa; font-size: 12px; margin-top: 24px; margin-bottom: 8px; }}
  a.refresh-btn {{ display: inline-block; color: #555; text-decoration: none;
                   border: 1px solid #ddd; padding: 5px 14px; border-radius: 6px;
                   font-size: 12px; margin-left: 8px; }}
  a.refresh-btn:hover {{ background: #f0f0f0; }}
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-left">
    <span class="logo">DataVault</span>
    <span class="proj">/ {proj_name}</span>
  </div>
  <div class="topbar-right">by {created_by}</div>
</div>

<div class="stats-bar">
  <div class="stat">
    <span class="stat-val">{len(history["files"])}</span>
    <span class="stat-lbl">Files tracked</span>
  </div>
  <div class="stat">
    <span class="stat-val">{total_versions}</span>
    <span class="stat-lbl">Total versions</span>
  </div>
  <div class="stat">
    <span class="stat-val">{sum(len(v.get("tags",[])) for d in history["files"].values() for v in d["versions"])}</span>
    <span class="stat-lbl">Tags</span>
  </div>
  <div class="stat">
    <span class="stat-val">SHA-256</span>
    <span class="stat-lbl">Hash algorithm</span>
  </div>
</div>

<div class="main">
  <div class="section-title">Tracked files</div>
  {file_cards}

  <div class="commands">
    <div class="commands-title">Quick reference</div>
    <div class="cmd-grid">
      <div class="cmd"><span>add</span> &lt;file&gt; "message"</div>
      <div class="cmd"><span>commit</span> &lt;file&gt; "message"</div>
      <div class="cmd"><span>verify</span> &lt;file&gt;</div>
      <div class="cmd"><span>log</span> &lt;file&gt;</div>
      <div class="cmd"><span>tag</span> &lt;file&gt; v2 "label"</div>
      <div class="cmd"><span>diff</span> &lt;file&gt; v1 v2</div>
      <div class="cmd"><span>checkout</span> &lt;file&gt; v1</div>
      <div class="cmd"><span>export</span></div>
    </div>
  </div>

  <p class="refresh-note">
    Data updates when you refresh.
    <a class="refresh-btn" href="/">↻ Refresh</a>
  </p>
</div>

</body>
</html>"""

def _error_page(message):
    return f"""<!DOCTYPE html><html><body style="font-family:sans-serif;padding:40px;color:#666">
    <h2 style="color:#1a1a1a">DataVault Dashboard</h2>
    <p style="margin-top:12px">{message}</p></body></html>"""

def _hash_file(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()

def _fmt_size(b):
    if b < 1024: return f"{b} B"
    if b < 1024*1024: return f"{b/1024:.1f} KB"
    return f"{b/1024/1024:.1f} MB"

# ── HTTP server ───────────────────────────────────────────────

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        html = build_dashboard_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, format, *args):
        pass  # suppress per-request logs

def main():
    if not os.path.exists(VAULT_DIR):
        print("No DataVault project found in this folder.")
        print("Run: python datavault.py init <name>")
        sys.exit(1)

    server = http.server.HTTPServer(("localhost", PORT), DashboardHandler)

    print(f"\nDataVault Dashboard running at:")
    print(f"  http://localhost:{PORT}")
    print(f"\nRefresh the browser after any commit, tag, or verify.")
    print(f"Press Ctrl+C to stop.\n")

    # Open browser automatically after short delay
    def open_browser():
        import time
        time.sleep(0.5)
        webbrowser.open(f"http://localhost:{PORT}")

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")

if __name__ == "__main__":
    main()