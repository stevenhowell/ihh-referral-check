"""Freeze one finished scan as static files for the public demo at /demo.

    python3 app/freeze_demo.py U01 --source "referral-1010-linh-pham-scan-medium.pdf"

Reads what the app saved for the packet in work/<id>/ (the review, the client profile, the
page transcripts, the page images) and the queue row the app would show, and writes them
under site/public/demo/ as demo.json plus one JPEG per page. The public page draws from
those files only: it never calls the API and never reaches back to this laptop.

Only run this on a packet made from invented data. IHH's de-identified packets (R01 to R11)
and anything derived from them must never be published: the script refuses to write an R
packet anywhere inside the repo. (Outside the repo, with --out, is allowed for a local preview.)
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common import REPO, WORK  # noqa: E402
import desk  # noqa: E402
import server  # noqa: E402

OUT = REPO / "site" / "public" / "demo"


def freeze(packet_id, out, source, note):
    out = out.resolve()
    if packet_id.startswith("R") and (out == REPO or REPO in out.parents):
        sys.exit("Refusing: R packets are IHH's real referrals and must never be published. "
                 "For a local preview, pass --out somewhere outside the repo.")
    d = WORK / packet_id
    review = json.loads((d / "review.json").read_text())
    profile = json.loads((d / "profile.json").read_text())
    pages = json.loads((d / "pages.json").read_text())
    if not (review["sha256"] == profile["sha256"] == pages["sha256"]):
        sys.exit("The review, profile and transcripts come from different files. Scan again, then freeze.")
    row = next(r for r in server.queue()["rows"] if r["id"] == packet_id)
    if row["state"] != "done":
        sys.exit(f"The scan isn't finished ({row['state']}).")

    out.mkdir(parents=True, exist_ok=True)
    pages_out = out / "pages"
    if pages_out.exists():
        shutil.rmtree(pages_out)
    pages_out.mkdir()
    images = []
    for png in sorted((d / "pages").glob("p-*.png")):
        jpg = png.with_suffix(".jpg")
        if not jpg.exists():
            from read_pages import _upload_bytes
            _upload_bytes(png)
        n = int(png.stem.split("-")[1])
        shutil.copyfile(jpg, pages_out / f"p-{n:02d}.jpg")
        images.append({"page": n, "src": f"/demo/pages/p-{n:02d}.jpg"})

    for key in ("usage",):  # token counts: not shown on the page
        review.pop(key, None)
    tasks = desk.tasks_for(packet_id, review)
    for t in tasks:  # the demo shows Fetch's suggested reviewer only; nothing a person recorded
        for key in ("done", "done_at", "outcome", "outcome_label", "note", "by", "outcomes", "owner_set_by_person"):
            t.pop(key, None)

    demo = {
        "frozen": {
            "packet_id": packet_id,
            "source_file": source,
            "scanned_at": review["reviewed_at"],
            "profile_built_at": profile["built_at"],
            "frozen_at": time.strftime("%Y-%m-%d %H:%M"),
            "model": review["model"],
            "note": note,
        },
        "queue": {k: row.get(k) for k in ("id", "uploaded", "state", "decision", "lean", "pages", "seconds",
                                           "flagged", "open_tasks", "profile_line", "scan_seconds", "added_at")},
        "review": review,
        "profile": profile,
        "tasks": tasks,
        "transcripts": {str(p["page"]): {k: p[k] for k in ("transcript", "kind", "rotated", "legibility",
                                                             "possible_unredacted_identifier")}
                        for p in pages["pages"]},
        "images": images,
    }
    (out / "demo.json").write_text(json.dumps(demo, indent=1))
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"Wrote {out}: demo.json, {len(images)} page images, {size / 1024:.0f} KB in all")
    return demo


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("packet_id", help="the packet as the app knows it, e.g. U01")
    ap.add_argument("--out", default=str(OUT), help=f"where to write (default {OUT})")
    ap.add_argument("--source", default="", help="the packet file's name, for the page's label")
    ap.add_argument("--note", default="A made-up referral from the hackathon's synthetic test set. Not a real patient.")
    a = ap.parse_args()
    freeze(a.packet_id, Path(a.out), a.source, a.note)
