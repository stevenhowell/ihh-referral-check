"""Steps 2 and 3: check the packet against IHH's rules, then check every quote.

Step 2 sends the page transcripts and IHH's rules to Claude and asks for a finding per
rule, each backed by the page number and the exact words from that page.

Step 3 is the quality check, and it does not use AI: every quote is looked up in the
transcript of the page it cites. A quote that is not there is flagged for the
coordinator, and a finding with no quote that checks out is marked unsupported.
"""

import json
import re
import time
from difflib import SequenceMatcher

import anthropic

from common import MODEL, criteria_prompt, packet_dir, rule_index
from read_pages import read_packet

STATUSES = ["ok", "problem", "cant_tell", "missing"]

EVIDENCE = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"page": {"type": "integer"}, "quote": {"type": "string"}},
        "required": ["page", "quote"],
        "additionalProperties": False,
    },
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "reason_for_hospital_stay": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string"},
                    "status": {"type": "string", "enum": STATUSES},
                    "headline": {"type": "string"},
                    "explanation": {"type": "string"},
                    "evidence": EVIDENCE,
                },
                "required": ["rule_id", "status", "headline", "explanation", "evidence"],
                "additionalProperties": False,
            },
        },
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "explanation": {"type": "string"},
                    "evidence": EVIDENCE,
                },
                "required": ["topic", "explanation", "evidence"],
                "additionalProperties": False,
            },
        },
        "suggestion": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["approve", "deny", "need_more_info"]},
                "lean_if_forced": {"type": "string", "enum": ["approve", "deny"]},
                "why": {"type": "string"},
                "deciding_rule_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["decision", "lean_if_forced", "why", "deciding_rule_ids"],
            "additionalProperties": False,
        },
        "ask_hospital": {"type": "array", "items": {"type": "string"}},
        "reply_draft": {"type": "string"},
    },
    "required": ["summary", "reason_for_hospital_stay", "findings", "conflicts", "suggestion",
                 "ask_hospital", "reply_draft"],
    "additionalProperties": False,
}

REVIEW_INSTRUCTIONS = """You are helping an Illumination Health + Home (IHH) referral coordinator review one hospital referral packet against IHH's admission rules (in the system prompt). The coordinator makes the decision. Your job is to show them, rule by rule, what the packet says, with the page number and the exact words, so they can check you in seconds.

The packet is above as page transcripts, made from faxed page images. It is a real referral with identifiers blacked out.

How to read it
- Check the chart, not only the referral form. The form is one person's summary and can be wrong. The deciding fact is often deep in the chart. When the form and the chart (or two chart pages) disagree, report it under conflicts.
- What the packet does not say is unknown, not normal. Use cant_tell.
- [redacted] marks a privacy redaction, not a missing document. Dates are redacted, so any rule that turns on a date or a number of hours is cant_tell; say "dates removed for privacy".
- When the outline and the referral form disagree, the outline wins (see "Which document wins"). Where the written rules are unclear (see the last section of the rules), say so in the explanation instead of guessing.
- Registered sex offender status is never a problem on its own: it is case by case. Report it as cant_tell for the coordinator.
- Some packets have no IHH referral form. That is a missing document, not a reason to stop.

Which rules to report
- One finding for the general criteria: the GEN rule the packet best supports.
- Every rule of kind must or exclude in the main rule list (ADL, MOB, MH, COG, OTH, INF and the rest), and every DOC item in the referral checklist.
- Every rule for a specific condition, treatment or device this patient has (for example the diabetes rules for a diabetic, IV rules for a patient with a PICC line, wound rules for a wound, cardiac rules after a heart procedure).
- Skip rules that plainly do not apply to this patient. Do not report FORM rules that a main-list rule already covers.

Statuses
- ok: the packet shows the rule is met. For a document item: the document is in the packet.
- problem: the packet shows something that breaks the rule or rules the patient out.
- cant_tell: the packet does not settle it.
- missing: a document item the hospital was asked to send is not in the packet.

Evidence
- Give at least one quote for every ok and problem finding, and for a conflict give one quote per side.
- Each quote must be copied character for character from the transcript of the page you cite, 4 to 30 words, one passage per quote. It will be checked automatically against that page; a quote that is not on the page is flagged as unreliable. Never paraphrase inside a quote and never combine words from two places.
- Use the page numbers from the "=== Page N" headers.

Headline: a few plain words a coordinator can scan, e.g. "Walks 150 ft with a walker". Explanation: one or two sentences.

Suggestion
- approve: nothing in the packet rules the patient out and the must rules are supported.
- deny: something in the packet rules the patient out under IHH's rules.
- need_more_info: the answer turns on something the hospital could send or confirm.
- lean_if_forced: the call you would make if the coordinator had to answer now with only this packet.
- why: two sentences at most, naming the rule IDs that decide it.

ask_hospital: short items the coordinator would request from the hospital case manager. Empty if nothing is needed.

reply_draft: a short message from the coordinator to the hospital case manager, 120 words at most. Refer to "the patient", never a name. Match the suggestion: for approve, say what is still needed before transport; for deny, a brief reason as IHH's form promises; for need_more_info, the list of what to send. It is a draft the coordinator will edit and send themselves."""


def _client():
    return anthropic.Anthropic(max_retries=6)


def _transcript_block(read):
    parts = []
    for p in read["pages"]:
        flags = []
        if p["rotated"]:
            flags.append("scanned sideways or upside down")
        if p["legibility"] != "clear":
            flags.append(p["legibility"].replace("_", " "))
        header = f"=== Page {p['page']} of {read['page_count']} ({p['kind'].replace('_', ' ')}"
        header += (", " + ", ".join(flags) if flags else "") + ") ==="
        parts.append(header + "\n" + p["transcript"].strip())
    return "\n\n".join(parts)


def ask_claude(read):
    started = time.time()
    with _client().messages.stream(
        model=MODEL,
        max_tokens=64000,
        system=[{"type": "text", "text": criteria_prompt(), "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "REFERRAL PACKET\n\n" + _transcript_block(read)},
            {"type": "text", "text": REVIEW_INSTRUCTIONS},
        ]}],
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "refusal":
        raise RuntimeError("Claude declined to review this packet.")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("The review was cut off before it finished.")
    text = next(b.text for b in message.content if b.type == "text")
    usage = {"input_tokens": message.usage.input_tokens, "output_tokens": message.usage.output_tokens,
             "cache_read_input_tokens": message.usage.cache_read_input_tokens or 0}
    return json.loads(text), usage, round(time.time() - started)


# ------------------------------------------------------------ quote check

def _words(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).split()


def _match(quote_words, page_words):
    """How closely the quote appears in the page: 1.0 is word for word."""
    n = len(quote_words)
    if not n or not page_words:
        return 0.0
    q = " ".join(quote_words)
    if q in " ".join(page_words):
        return 1.0
    # Cheap filter before the slower fuzzy search.
    vocab = set(page_words)
    if sum(w in vocab for w in quote_words) / n < 0.6:
        return 0.0
    # Only try windows that start near one of the quote's first words.
    starts = set(quote_words[:3])
    best = 0.0
    for i, word in enumerate(page_words):
        if word not in starts:
            continue
        for start in range(max(0, i - 2), i + 1):
            for length in (n - 1, n, n + 1):
                window = page_words[start:start + length]
                best = max(best, SequenceMatcher(None, quote_words, window, autojunk=False).ratio())
        if best > 0.97:
            break
    return best


def check_quote(evidence, page_words):
    """Label one quote: on_page, close (small transcription differences), other_page or not_found."""
    qw = _words(evidence["quote"])
    # A near match never excuses a different number: "50 ft" is not "150 ft".
    numbers = {w for w in qw if any(ch.isdigit() for ch in w)}

    def near(words):
        return _match(qw, words) >= 0.8 and numbers <= set(words)

    cited = page_words.get(evidence["page"], [])
    if _match(qw, cited) >= 0.999:
        return {"check": "on_page"}
    if near(cited):
        return {"check": "close"}
    for page, words in page_words.items():
        if page != evidence["page"] and near(words):
            return {"check": "other_page", "found_on": page}
    return {"check": "not_found"}


def check_review(review, read):
    page_words = {p["page"]: _words(p["transcript"]) for p in read["pages"]}
    counts = {"quotes": 0, "on_page": 0, "close": 0, "other_page": 0, "not_found": 0, "bad_page": 0}
    for item in review["findings"] + review["conflicts"]:
        for ev in item["evidence"]:
            counts["quotes"] += 1
            if ev["page"] not in page_words:
                ev.update({"check": "not_found", "bad_page": True})
                counts["bad_page"] += 1
                counts["not_found"] += 1
                continue
            ev.update(check_quote(ev, page_words))
            counts[ev["check"]] += 1
    for f in review["findings"]:
        good = [e for e in f["evidence"] if e["check"] in ("on_page", "close")]
        f["supported"] = bool(good) or f["status"] in ("cant_tell", "missing")
    return counts


# ------------------------------------------------------------------- run

def review_packet(packet_id, progress=lambda text: None, fresh=False):
    out = packet_dir(packet_id) / "review.json"
    if out.exists() and not fresh:
        return json.loads(out.read_text())

    started = time.time()
    read = read_packet(packet_id, progress)
    progress(f"Checking {read['page_count']} pages against IHH's rules")
    review, usage, review_seconds = ask_claude(read)
    progress("Checking every quote against its page")
    counts = check_review(review, read)

    rules = rule_index()
    for f in review["findings"]:
        rule = rules.get(f["rule_id"])
        f["rule_text"] = rule["text"] if rule else None
        f["rule_section"] = rule["section"] if rule else None
        f["known_rule"] = rule is not None

    result = {
        "packet_id": packet_id,
        "page_count": read["page_count"],
        "pages": [{k: p[k] for k in ("page", "kind", "rotated", "legibility", "possible_unredacted_identifier")}
                  for p in read["pages"]],
        "review": review,
        "quote_check": counts,
        "seconds": round(time.time() - started),
        "review_seconds": review_seconds,
        "usage": {"read": read.get("usage"), "review": usage},
        "model": MODEL,
        "reviewed_at": time.strftime("%Y-%m-%d %H:%M"),
    }
    out.write_text(json.dumps(result, indent=1))
    return result


if __name__ == "__main__":
    import sys
    from common import load_env
    load_env()
    r = review_packet(sys.argv[1], progress=print, fresh="--fresh" in sys.argv)
    s = r["review"]["suggestion"]
    print(json.dumps({"decision": s["decision"], "lean": s["lean_if_forced"], "why": s["why"],
                      "quote_check": r["quote_check"], "seconds": r["seconds"]}, indent=1))
