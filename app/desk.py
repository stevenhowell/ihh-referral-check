"""The coordinator's desk: decisions, risk tasks and their owners, and beds available.

Everything a person records is kept in work/desk.json, so it survives a refresh or a
restart. Fetch never fills any of it in on its own: decisions and bed counts are
typed by a person, and each task's owner starts from a default a person can change.
"""

import json
import threading
import time

from common import WORK, packet_path

DESK = WORK / "desk.json"
LOCK = threading.Lock()

OWNERS = ["Coordinator", "Nurse (LVN)", "Clinical lead", "Program manager"]

# Default owner for a risk, by the kind of rule it touches. These are our proposal,
# not IHH's: every owner can be changed on screen.
CLINICAL = {"CARD", "CIR", "NEU", "RESP", "RSP", "ID", "INT", "GI", "GU", "END", "DM", "MSK", "EOL", "OPH", "INF"}
NURSING = {"ADL", "MOB", "COG"}
PROGRAM = {"OTH", "MH"}

KIND_LABEL = {"problem": "Rules them out", "coordinator_call": "Your call", "arrange": "Arrange first",
              "conflict": "Pages disagree", "unchecked": "Check by hand"}


def _load():
    if DESK.exists():
        return json.loads(DESK.read_text())
    return {"decisions": {}, "tasks": {}, "beds": None, "added": {}}


def _save(desk):
    DESK.write_text(json.dumps(desk, indent=1))


def snapshot():
    with LOCK:
        return _load()


def added_at(packet_id):
    """When the packet entered Fetch. The fax's own date is blacked out, so this is not the fax time."""
    with LOCK:
        desk = _load()
        if packet_id not in desk["added"]:
            desk["added"][packet_id] = packet_path(packet_id).stat().st_mtime
            _save(desk)
        return desk["added"][packet_id]


def default_owner(kind, rule_id):
    if kind in ("conflict", "unchecked", "arrange"):
        return "Coordinator"
    prefix = (rule_id or "").split("-")[0]
    if prefix in PROGRAM:
        return "Program manager"
    if prefix in NURSING:
        return "Nurse (LVN)"
    if prefix in CLINICAL:
        return "Clinical lead"
    return "Coordinator"


def tasks_for(packet_id, review):
    """Every flagged item in a review becomes a task, merged with what people have recorded."""
    with LOCK:
        saved = _load()["tasks"]
    rv = review["review"]
    out = []

    def add(key, kind, finding, title):
        tid = f"{packet_id}:{key}"
        rec = saved.get(tid, {})
        ev = finding["evidence"][0] if finding.get("evidence") else None
        out.append({
            "id": tid, "packet_id": packet_id, "kind": kind, "kind_label": KIND_LABEL[kind],
            "title": title, "detail": finding.get("explanation", ""), "rule_id": finding.get("rule_id"),
            "evidence": ev,
            "owner": rec.get("owner") or default_owner(kind, finding.get("rule_id")),
            "owner_set_by_person": bool(rec.get("owner")),
            "done": rec.get("done", False), "done_at": rec.get("done_at"),
        })

    flag = ("problem", "coordinator_call", "arrange")
    for f in rv["findings"]:
        if f["status"] in flag:
            add(f"{f['status']}:{f['rule_id']}", f["status"], f, f["headline"])
    for i, c in enumerate(rv["conflicts"]):
        add(f"conflict:{i}", "conflict", c, c["topic"])
    for f in rv["findings"]:
        if f["status"] not in flag and f.get("supported") is False:
            add(f"unchecked:{f['rule_id']}", "unchecked", f, f["headline"])
    order = {"problem": 0, "coordinator_call": 1, "arrange": 2, "conflict": 3, "unchecked": 4}
    out.sort(key=lambda t: (t["done"], order[t["kind"]]))
    return out


def set_task(task_id, owner=None, done=None):
    with LOCK:
        desk = _load()
        rec = desk["tasks"].setdefault(task_id, {})
        if owner is not None:
            if owner not in OWNERS:
                raise ValueError("Unknown owner")
            rec["owner"] = owner
        if done is not None:
            rec["done"] = bool(done)
            rec["done_at"] = time.time() if done else None
        _save(desk)


def set_decision(packet_id, decision):
    with LOCK:
        desk = _load()
        if decision is None:
            desk["decisions"].pop(packet_id, None)
        elif decision in ("approve", "deny"):
            desk["decisions"][packet_id] = {"decision": decision, "at": time.time()}
        else:
            raise ValueError("Decision must be approve or deny")
        _save(desk)


def set_beds(count):
    with LOCK:
        desk = _load()
        if count is None:
            desk["beds"] = None
        else:
            count = int(count)
            if not 0 <= count <= 500:
                raise ValueError("Bed count out of range")
            desk["beds"] = {"count": count, "at": time.time()}
        _save(desk)
