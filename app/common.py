"""Paths, settings and IHH's criteria, shared by every part of the app."""

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHALLENGE = REPO / "challenges" / "1-referral-intake"
PACKETS = CHALLENGE / "packets"
CRITERIA_DIR = CHALLENGE / "criteria"
DECISIONS = CHALLENGE / "eval" / "decisions.json"  # read only by scoring, never by a review

# Everything derived from a packet lives here and is git-ignored.
WORK = REPO / "work"
UPLOADS = WORK / "uploads"

MODEL = "claude-opus-5-5"


def load_env():
    """Read KEY=VALUE lines from .env at the repo root without overriding the shell."""
    env = REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def packet_path(packet_id):
    """R01..R11 come from the event folder; U01.. are packets opened in the app."""
    if packet_id.startswith("U"):
        return UPLOADS / f"{packet_id}.pdf"
    return PACKETS / f"{packet_id}.pdf"


class ChangedFile(Exception):
    """The packet file is not the one that was read. Its results must not be shown."""


_FINGERPRINTS = {}


def fingerprint(packet_id):
    """SHA-256 of the packet file, cached until the file's size or time changes."""
    path = packet_path(packet_id)
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _FINGERPRINTS:
        import hashlib
        _FINGERPRINTS[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _FINGERPRINTS[key]


def protect(path):
    """Originals are read only: nothing in the app may write to them."""
    path.chmod(0o444)


def packet_dir(packet_id):
    d = WORK / packet_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- criteria

def _criteria():
    return json.loads((CRITERIA_DIR / "admission-criteria.json").read_text())


def rule_index():
    """Every rule ID IHH's documents define, with its text and where it comes from."""
    c = _criteria()
    rules = {}
    for r in c["general"]["any_of"]:
        rules[r["id"]] = {"text": r["text"], "section": "General (meets one or more)", "kind": "must"}
    for r in c["rules"]:
        rules[r["id"]] = {"text": r["text"], "section": r["section"], "kind": r["kind"]}
    for system in c["by_system"]:
        for r in system["eligible"]:
            rules[r["id"]] = {"text": r["text"], "section": f"{system['system']}: eligible", "kind": "eligible"}
        for r in system["ineligible"]:
            rules[r["id"]] = {"text": r["text"], "section": f"{system['system']}: ineligible", "kind": "exclude"}
    for r in c["referral_checklist"]["items"]:
        rules[r["id"]] = {"text": r["text"], "section": "Referral checklist", "kind": "document"}
    form = c["referral_form_screen"]
    for r in form["must_meet_all"]:
        rules[r["id"]] = {"text": r["text"], "section": "Referral form: must meet", "kind": "must",
                          "superseded_by": r.get("superseded_by")}
    for r in form["not_eligible_if"]:
        rules[r["id"]] = {"text": r["text"], "section": "Referral form: not eligible if", "kind": "exclude",
                          "superseded_by": r.get("superseded_by")}
    return rules


def criteria_prompt():
    """IHH's rules as one stable block of text. It is identical for every packet, so it caches."""
    c = _criteria()
    lines = [
        "# IHH recuperative care admission rules (adults)",
        "",
        "Rule kinds: " + "; ".join(f"{k} = {v}" for k, v in c["kinds"].items()),
        "",
        "Which document wins: " + c["precedence"],
        "",
        "## General: " + c["general"]["rule"],
    ]
    lines += [f"- {r['id']}: {r['text']}" for r in c["general"]["any_of"]]
    section = None
    for r in c["rules"]:
        if r["section"] != section:
            section = r["section"]
            lines += ["", f"## {section}"]
        extra = " (needs human review)" if r.get("human_review") else ""
        lines.append(f"- {r['id']} [{r['kind']}]{extra}: {r['text']}")
    lines += ["", "## Specific conditions by body system"]
    for system in c["by_system"]:
        lines += ["", f"### {system['system']}", "Eligible:"]
        lines += [f"- {r['id']}: {r['text']}" for r in system["eligible"]]
        lines.append("Ineligible:")
        lines += [f"- {r['id']}: {r['text']}" for r in system["ineligible"]]
    form = c["referral_form_screen"]
    lines += ["", "## Referral form screen (form RC0725-SH; the outline above wins where they differ)",
              "Must meet all:"]
    lines += [f"- {r['id']}: {r['text']}" + (f" (superseded by {r['superseded_by']})" if r.get("superseded_by") else "")
              for r in form["must_meet_all"]]
    lines.append("Not eligible if:")
    lines += [f"- {r['id']}: {r['text']}" + (f" (superseded by {r['superseded_by']})" if r.get("superseded_by") else "")
              for r in form["not_eligible_if"]]
    lines += ["", "## Referral checklist: documents the hospital sends"]
    lines += [f"- {r['id']}: {r['text']}" for r in c["referral_checklist"]["items"]]

    # The organizers' list of places where the written rules run out.
    md = (CRITERIA_DIR / "admission-criteria.md").read_text()
    gaps = md.split("## Places where the written rules are unclear", 1)
    if len(gaps) == 2:
        lines += ["", "## Places where the written rules are unclear", gaps[1].strip()]
    return "\n".join(lines)
