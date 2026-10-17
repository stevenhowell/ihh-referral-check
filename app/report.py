"""The exported record for one referral: the coordinator's decision and the review behind it.

Built as a printable page and turned into a PDF by headless Chrome. It states what was
decided, by whom, when, and on what evidence, with page numbers back to the original fax
and the fax's SHA-256 so the record can be tied to the exact file. Fetch's suggestion is
labeled as a suggestion; only the coordinator's decision is a decision.
"""

import html
import json
import subprocess
import tempfile
import time
from pathlib import Path

import desk
from common import WORK, packet_path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CALL = {"approve": "Approve", "approve_once_arranged": "Approve once arranged", "deny": "Deny",
        "need_more_info": "Needs more information"}
STATUS = {"ok": "Meets", "problem": "Rules out", "arrange": "Arrange first", "coordinator_call": "Coordinator's call",
          "cant_tell": "Not in the fax", "missing": "Missing document"}


def _e(x):
    return html.escape(str(x if x is not None else ""))


def _t(ts):
    return time.strftime("%b %d, %Y %I:%M %p", time.localtime(ts)) if ts else "–"


def _quotes(evidence):
    rows = []
    for e in evidence:
        ok = e.get("check") in ("on_page", "close") and e.get("image_check", "yes") == "yes"
        rows.append(f'<div class="q"><span class="pg">p. {e["page"]}</span> “{_e(e["quote"])}”'
                    f'{"" if ok else " <b>(check by hand)</b>"}</div>')
    return "".join(rows)


def report_html(packet_id):
    r = json.loads((WORK / packet_id / "review.json").read_text())
    rv, s = r["review"], r["review"]["suggestion"]
    d = desk.snapshot()
    decision = d["decisions"].get(packet_id)
    pf = WORK / packet_id / "profile.json"
    profile = json.loads(pf.read_text()) if pf.exists() else None
    tasks = desk.tasks_for(packet_id, r)
    log = [x for x in d.get("log", []) if x["packet"] == packet_id]
    name = f"Packet {packet_id}" if packet_id.startswith("R") else f"Opened packet {packet_id[1:]}"

    if decision:
        took = decision.get("seconds_to_decide")
        reason = f"<div>Reason: {_e(decision['note'])}</div>" if decision.get("note") else ""
        dec = (f'<div class="decision {decision["decision"]}"><div class="lbl">Coordinator decision</div>'
               f'<div class="big">{"Approved" if decision["decision"] == "approve" else "Denied"}</div>'
               f'<div>By {_e(decision.get("by"))} on {_t(decision["at"])}'
               f'{f" · decided {took // 60} min {took % 60} s after opening" if took else ""}</div>'
               f'{reason}</div>')
    else:
        dec = '<div class="decision none"><div class="lbl">Coordinator decision</div><div class="big">Not decided yet</div><div>This record shows Fetch\'s review only.</div></div>'

    flagged = [f for f in rv["findings"] if f["status"] in ("problem", "coordinator_call", "arrange")]
    task_by_rule = {t["rule_id"]: t for t in tasks if t.get("rule_id")}
    flag_rows = "".join(
        f'<tr><td>{_e(STATUS[f["status"]])}</td><td><b>{_e(f["headline"])}</b><br>{_e(f["explanation"])}'
        f'<div class="rule">IHH rule {_e(f["rule_id"])}: {_e(f.get("rule_text"))}</div>{_quotes(f["evidence"])}</td>'
        f'<td>{_e(task_by_rule.get(f["rule_id"], {}).get("owner", ""))}<br>'
        f'{"Done" if task_by_rule.get(f["rule_id"], {}).get("done") else "Open"}</td></tr>'
        for f in flagged)
    conflict_rows = "".join(f'<tr><td>Pages disagree</td><td><b>{_e(c["topic"])}</b><br>{_e(c["explanation"])}{_quotes(c["evidence"])}</td><td></td></tr>'
                            for c in rv["conflicts"])
    rule_rows = "".join(f'<tr><td>{_e(f["rule_id"])}</td><td>{_e(STATUS[f["status"]])}</td><td>{_e(f["headline"])}</td>'
                        f'<td>{", ".join("p. " + str(e["page"]) for e in f["evidence"]) or "–"}</td></tr>'
                        for f in rv["findings"])
    prof = ""
    if profile and profile.get("sha256") == r.get("sha256"):
        P = profile["profile"]
        prof = "<h2>Client profile</h2><p>" + _e(P["one_line"]) + "</p><table class='kv'>" + "".join(
            f'<tr><td>{_e(f["label"])}</td><td>{_e(f["value"])}{" (referral form only)" if f.get("form_only") else ""}</td>'
            f'<td>{", ".join("p. " + str(e["page"]) for e in f["evidence"]) or "–"}</td></tr>'
            for sec in P["sections"] for f in sec["facts"]) + "</table>"
    todo = "".join(f"<li>{_e(x)}</li>" for x in (rv.get("arrange_first") or []) + rv["ask_hospital"])
    qc = r["quote_check"]
    img = qc.get("image") or {}
    log_rows = "".join(f'<tr><td>{_t(x["at"])}</td><td>{_e(x["action"])}</td><td>{_e(x.get("by") or "")}</td>'
                       f'<td>{_e(x["detail"] if isinstance(x["detail"], str) else "")}</td></tr>' for x in log)

    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Fetch record {packet_id}</title>
<style>
body {{ font: 11pt/1.45 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #111; margin: 0; }}
h1 {{ font-size: 18pt; margin: 0; }} h2 {{ font-size: 13pt; margin: 22px 0 8px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }}
.head {{ display: flex; justify-content: space-between; border-bottom: 2px solid #111; padding-bottom: 8px; }}
.meta {{ color: #555; font-size: 9pt; }}
.decision {{ border: 2px solid #111; border-radius: 8px; padding: 10px 14px; margin: 14px 0; }}
.decision.approve {{ border-color: #1f7a3a; }} .decision.deny {{ border-color: #c4291c; }} .decision.none {{ border-style: dashed; }}
.lbl {{ font-size: 9pt; text-transform: uppercase; letter-spacing: .05em; color: #555; }} .big {{ font-size: 16pt; font-weight: 700; }}
table {{ width: 100%; border-collapse: collapse; font-size: 9.5pt; }} td, th {{ border-top: 1px solid #ddd; padding: 5px 6px; vertical-align: top; text-align: left; }}
.rule {{ color: #555; font-size: 8.5pt; margin-top: 3px; }} .q {{ font-style: italic; margin-top: 3px; }} .pg {{ font-style: normal; font-weight: 700; }}
.kv td:first-child {{ width: 22%; color: #555; }}
.note {{ background: #f4f4f4; padding: 8px 10px; border-radius: 6px; font-size: 9pt; margin-top: 18px; }}
tr {{ page-break-inside: avoid; }} h2 {{ page-break-after: avoid; }} thead {{ display: table-header-group; }}
</style></head><body>
<div class="head"><div><h1>Referral decision record · {_e(name)}</h1>
<div class="meta">Illumination Health + Home · recuperative care referral · made with Fetch, a prototype</div></div>
<div class="meta" style="text-align:right">Exported {_t(time.time())}<br>Fax: {r["page_count"]} pages<br>File SHA-256 {_e(r.get("sha256", "")[:16])}…</div></div>
{dec}
<h2>Fetch's suggestion (not a decision)</h2>
<p><b>{_e(CALL[s["decision"]])}{", leaning " + _e(s["lean_if_forced"]) if s["decision"] == "need_more_info" else ""}.</b> {_e(s["why"])}</p>
<p class="meta">Reviewed {_e(r.get("reviewed_at"))} with {_e(r.get("model"))}. {qc["on_page"] + qc["close"]} of {qc["quotes"]} quotes found in the page text; {img.get("seen", "–")} of {img.get("checked", "–")} seen on the page image.</p>
{"<h2>Before admission</h2><ul>" + todo + "</ul>" if todo else ""}
<h2>Flagged for the coordinator</h2>
<table><thead><tr><th style="width:14%">Type</th><th>Finding and evidence (page and exact words from the fax)</th><th style="width:15%">Reviewer · status</th></tr></thead>{flag_rows}{conflict_rows}</table>
{prof}
<h2>Every rule checked</h2>
<table><thead><tr><th style="width:11%">Rule</th><th style="width:16%">Result</th><th>Finding</th><th style="width:14%">Pages</th></tr></thead>{rule_rows}</table>
<h2>Record of changes</h2>
{"<table><thead><tr><th>When</th><th>Action</th><th>By</th><th>Note</th></tr></thead>" + log_rows + "</table>" if log_rows else "<p class='meta'>No changes recorded.</p>"}
<div class="note">Names, dates and other identifiers were blacked out in the fax before Fetch read it, and this record contains none. Fetch's suggestion is produced by AI and every finding cites the fax page it came from; the coordinator's decision is the only decision. Built at the Orange County Claude Impact Lab as a prototype; it is not connected to any IHH system.</div>
</body></html>"""


def export_pdf(packet_id):
    out_dir = WORK / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / f"Fetch-{packet_id}-record.pdf"
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir=out_dir) as f:
        f.write(report_html(packet_id))
        page = Path(f.name)
    try:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", page.as_uri()], check=True, capture_output=True, timeout=120)
    finally:
        page.unlink(missing_ok=True)
    return pdf
