"""Local web app for the referral check. Run: python3 app/server.py, then open http://localhost:8811

Nothing here sends anything anywhere except the packet pages to the Claude API.
"""

import json
import re
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common import DECISIONS, PACKETS, UPLOADS, WORK, fingerprint, load_env, packet_path, protect  # noqa: E402
from review import review_packet  # noqa: E402
import desk  # noqa: E402
from client_profile import build_profile  # noqa: E402

STATIC = Path(__file__).parent / "static"
PORT = 8811
JOBS = {}  # packet_id -> {"state": "running" | "error", "step": str}
LOCK = threading.Lock()
# A few reviews at once keeps each one fast and stays under the API's rate limits.
SLOTS = threading.Semaphore(3)


def packet_ids():
    ids = sorted(p.stem for p in PACKETS.glob("R[0-9][0-9].pdf"))
    if UPLOADS.exists():
        ids += sorted(p.stem for p in UPLOADS.glob("U[0-9][0-9].pdf"))
    return ids


def summary(packet_id):
    review = WORK / packet_id / "review.json"
    with LOCK:
        job = dict(JOBS.get(packet_id, {}))
    item = {"id": packet_id, "uploaded": packet_id.startswith("U")}
    if job.get("state") == "running":
        item.update(state="running", step=job.get("step"))
    elif job.get("state") == "error":
        item.update(state="error", error=job.get("error"))
    elif status := running_elsewhere(packet_id):  # a run in progress outranks an older result
        item.update(state="running", step=status)
    elif review.exists() and not matches_file(packet_id):
        item.update(state="changed")
    elif review.exists():
        r = json.loads(review.read_text())
        s = r["review"]["suggestion"]
        fs = r["review"]["findings"]
        flag = ("problem", "arrange", "coordinator_call")
        flagged = (sum(f["status"] in flag for f in fs) + len(r["review"]["conflicts"])
                   + sum(f["status"] not in flag and f.get("supported") is False for f in fs))
        item.update(state="done", decision=s["decision"], lean=s["lean_if_forced"],
                    pages=r["page_count"], seconds=r["seconds"], flagged=flagged)
    else:
        item.update(state="new")
    return item


def matches_file(packet_id):
    """A result is shown only for the exact file it was made from."""
    r = json.loads((WORK / packet_id / "review.json").read_text())
    try:
        return r.get("sha256") == fingerprint(packet_id)
    except FileNotFoundError:
        return False


def running_elsewhere(packet_id):
    """A review started from a terminal leaves its current step in status.json."""
    f = WORK / packet_id / "status.json"
    if not f.exists():
        return None
    status = json.loads(f.read_text())
    return status["step"] if time.time() - status["at"] < 600 else None


def start(packet_id, fresh=False):
    with LOCK:
        if JOBS.get(packet_id, {}).get("state") == "running":
            return
        JOBS[packet_id] = {"state": "running", "step": "Waiting for another review to finish"}

    def step(text):
        with LOCK:
            JOBS[packet_id]["step"] = text

    def run():
        try:
            with SLOTS:
                step("Starting")
                review_packet(packet_id, progress=step, fresh=fresh)
                build_profile(packet_id, progress=step)
            with LOCK:
                JOBS.pop(packet_id, None)
        except Exception as exc:  # shown to the coordinator as the reason the review stopped
            traceback.print_exc()
            with LOCK:
                JOBS[packet_id] = {"state": "error", "error": friendly_error(exc)}

    threading.Thread(target=run, daemon=True).start()


def friendly_error(exc):
    text = str(exc)
    name = type(exc).__name__
    if "api_key" in text.lower() or "authentication" in name.lower() or "auth" in text.lower():
        return "No working Claude API key. Add ANTHROPIC_API_KEY to the .env file and restart the app."
    if "RateLimit" in name:
        return "Claude's rate limit was reached. Wait a minute, then choose Review again."
    if "credit" in text.lower() or "billing" in text.lower():
        return "The Claude API account is out of credit."
    return f"The review stopped: {text[:300]}"


def file_kind(data):
    if data.startswith(b"%PDF"):
        return "pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return "heic"
    return None


def page_count(pdf):
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(m.group(1)) if m else 0


def queue():
    """Every packet as a row of the coordinator's worklist, plus the dashboard counts."""
    d = desk.snapshot()
    rows, tasks = [], []
    for pid in packet_ids():
        item = summary(pid)
        item["added_at"] = desk.added_at(pid)
        item["coordinator"] = d["decisions"].get(pid)
        if item["state"] == "done":
            r = json.loads((WORK / pid / "review.json").read_text())
            t = desk.tasks_for(pid, r)
            tasks += t
            item["open_tasks"] = sum(not x["done"] for x in t)
            item["profile_line"] = None
            pf = WORK / pid / "profile.json"
            if pf.exists():
                prof = json.loads(pf.read_text())
                if prof.get("sha256") == r.get("sha256"):
                    item["profile_line"] = prof["profile"]["one_line"]
        rows.append(item)
    undecided = [x for x in rows if not x["coordinator"]]
    lean = lambda x: call_of(x["decision"], x["lean"])
    counts = {
        "to_review": len(undecided),
        "suggest_approve": sum(x["state"] == "done" and lean(x) == "approve" for x in undecided),
        "suggest_deny": sum(x["state"] == "done" and lean(x) == "deny" for x in undecided),
        "to_look_at": sum(x.get("open_tasks", 0) > 0 for x in undecided),
        "approved": sum((x["coordinator"] or {}).get("decision") == "approve" for x in rows),
        "denied": sum((x["coordinator"] or {}).get("decision") == "deny" for x in rows),
    }
    return {"rows": rows, "tasks": tasks, "counts": counts, "beds": d["beds"], "owners": desk.OWNERS, "now": time.time()}


def score():
    """Compare finished reviews with IHH's real decisions. The only place decisions.json is read."""
    truth = {p["packet_id"]: p["decision"] for p in json.loads(DECISIONS.read_text())["packets"]}
    rows = []
    for pid in sorted(truth):
        item = summary(pid)
        row = {"id": pid, "ihh": truth[pid], "state": item["state"]}
        if item["state"] == "done":
            r = json.loads((WORK / pid / "review.json").read_text())
            row.update(decision=item["decision"], lean=item["lean"], pages=item["pages"],
                       seconds=item["seconds"], quote_check=r["quote_check"],
                       why=r["review"]["suggestion"]["why"])
            row["match"] = call_of(item["decision"], item["lean"]) == truth[pid]
        before = WORK / pid / "review-v1.json"
        if before.exists():
            b = json.loads(before.read_text())["review"]["suggestion"]
            row["before"] = {"decision": b["decision"], "lean": b["lean_if_forced"],
                             "match": call_of(b["decision"], b["lean_if_forced"]) == truth[pid]}
        rows.append(row)
    return {"rows": rows, "denials": denial_reasons(truth), "audit": audit_summary()}


def audit_summary():
    """Totals from the independent audits in work/audit: each one re-read the fax and graded Fetch's claims."""
    files = sorted((WORK / "audit").glob("R*.json"))
    if not files:
        return None
    rows, tot, types = [], {"correct": 0, "partly": 0, "wrong": 0, "unverifiable": 0}, {}
    for f in files:
        a = json.loads(f.read_text())
        v = {k: sum(c["verdict"] == k for c in a["claims"]) for k in tot}
        for k in tot:
            tot[k] += v[k]
        terr = 0
        for page in a["transcript_spotcheck"]:
            for e in page.get("errors", []):
                types[e["type"]] = types.get(e["type"], 0) + 1
                terr += 1
        rows.append({"id": a["packet"], "claims": len(a["claims"]), **v, "transcript_errors": terr,
                     "missed_high": sum(m["severity"] == "high" for m in a["missed"]),
                     "summary": a.get("summary", "")})
    return {"rows": rows, "totals": tot, "transcript_types": types,
            "graded": "the version before the accuracy fixes (v2)"}


def call_of(decision, lean):
    """The approve or deny Fetch's suggestion amounts to, for comparing with IHH."""
    if decision in ("approve", "approve_once_arranged"):
        return "approve"
    if decision == "deny":
        return "deny"
    return lean


def denial_reasons(truth):
    """Our after-the-fact reading of why IHH denied each packet, kept in work/denial-reasons.json.

    Written with the decision known, so a review must never see it. It is shown only here,
    next to the score, and compared with what the review flagged on its own.
    """
    f = WORK / "denial-reasons.json"
    if not f.exists():
        return None
    reasons = json.loads(f.read_text())["packets"]
    out = []
    for pid in sorted(p for p, d in truth.items() if d == "deny"):
        entry = dict(reasons.get(pid) or {})
        entry["id"] = pid
        review = WORK / pid / "review.json"
        if entry.get("rule_ids") and review.exists():
            rv = json.loads(review.read_text())["review"]
            flagged = {x["rule_id"] for x in rv["findings"] if x["status"] == "problem"}
            flagged |= set(rv["suggestion"]["deciding_rule_ids"])
            entry["tool_flagged"] = sorted(flagged & set(entry["rule_ids"]))
        out.append(entry)
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self.send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/packets":
            return self.send(200, {"packets": [summary(p) for p in packet_ids()]})
        if path == "/api/queue":
            return self.send(200, queue())
        m = re.match(r"^/api/profile/([RU]\d{2})$", path)
        if m:
            f = WORK / m.group(1) / "profile.json"
            if not f.exists():
                return self.send(404, {"error": "No profile yet"})
            prof = json.loads(f.read_text())
            if prof.get("sha256") != fingerprint(m.group(1)):
                return self.send(409, {"error": "The file changed after the profile was built."})
            return self.send(200, prof)
        if path == "/api/score":
            return self.send(200, score())
        m = re.match(r"^/api/review/([RU]\d{2})$", path)
        if m:
            f = WORK / m.group(1) / "review.json"
            if not f.exists():
                return self.send(404, {"error": "Not reviewed yet"})
            if not matches_file(m.group(1)):
                return self.send(409, {"error": "This file changed after it was reviewed, so the review isn't shown."})
            result = json.loads(f.read_text())
            clear = WORK / "redaction-clearances.json"
            if clear.exists():
                result["cleared"] = json.loads(clear.read_text()).get(m.group(1), {})
            return self.send(200, result)
        m = re.match(r"^/api/transcript/([RU]\d{2})/(\d+)$", path)
        if m:
            f = WORK / m.group(1) / "pages.json"
            if not f.exists():
                return self.send(404, {"error": "Not read yet"})
            pages = json.loads(f.read_text())["pages"]
            page = next((p for p in pages if p["page"] == int(m.group(2))), None)
            return self.send(200, page) if page else self.send(404, {"error": "No such page"})
        m = re.match(r"^/page/([RU]\d{2})/(\d+)\.png$", path)
        if m:
            images = sorted((WORK / m.group(1) / "pages").glob("p-*.png"))
            n = int(m.group(2))
            if 1 <= n <= len(images):
                return self.send(200, images[n - 1].read_bytes(), "image/png")
            return self.send(404, {"error": "No such page"})
        self.send(404, {"error": "Not found"})

    def body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            m = re.match(r"^/api/decision/([RU]\d{2})$", path)
            if m:
                desk.set_decision(m.group(1), self.body().get("decision"))
                return self.send(200, {"ok": True})
            if path == "/api/task":
                b = self.body()
                desk.set_task(b["id"], owner=b.get("owner"), done=b.get("done"))
                return self.send(200, {"ok": True})
            if path == "/api/beds":
                desk.set_beds(self.body().get("count"))
                return self.send(200, {"ok": True})
        except (ValueError, KeyError) as exc:
            return self.send(400, {"error": str(exc)})
        m = re.match(r"^/api/review/([RU]\d{2})$", path)
        if m:
            pid = m.group(1)
            if not packet_path(pid).exists():
                return self.send(404, {"error": "That packet is not in the packets folder."})
            start(pid, fresh="fresh=1" in self.path)
            return self.send(202, summary(pid))
        if path == "/api/upload":
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)
            kind = file_kind(data)
            if not kind:
                return self.send(400, {"error": "Open a PDF or a photo (JPEG, PNG or HEIC) of the fax."})
            UPLOADS.mkdir(parents=True, exist_ok=True)
            n = len(list(UPLOADS.glob("U[0-9][0-9].pdf"))) + 1
            pid = f"U{n:02d}"
            target = UPLOADS / f"{pid}.pdf"
            if kind == "pdf":
                target.write_bytes(data)
            else:
                # A phone photo becomes a one-page PDF, so it goes through the same steps as a fax.
                photo = UPLOADS / f"{pid}.{kind}"
                photo.write_bytes(data)
                done = subprocess.run(["sips", "-s", "format", "pdf", str(photo), "--out", str(target)],
                                      capture_output=True)
                if done.returncode or not target.exists():
                    return self.send(400, {"error": "That photo couldn't be opened. Try a PDF or a JPEG."})
            protect(target)
            pages = page_count(target)
            if pages > 150:
                target.chmod(0o644)
                target.unlink()
                return self.send(400, {"error": f"That file has {pages} pages. The review handles up to 150."})
            start(pid)
            return self.send(202, summary(pid))
        self.send(404, {"error": "Not found"})


if __name__ == "__main__":
    load_env()
    for pdf in list(PACKETS.glob("R[0-9][0-9].pdf")) + list(UPLOADS.glob("U[0-9][0-9].pdf")):
        protect(pdf)
    print(f"Referral check running at http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
