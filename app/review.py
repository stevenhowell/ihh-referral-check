"""Steps 2 to 4: check the packet against IHH's rules, then check every quote twice.

Step 2 sends the page transcripts and IHH's rules to Claude and asks for a finding per
rule, each backed by the page number and the exact words from that page.

Step 3 is the quality check, and it does not use AI: every quote is looked up in the
transcript of the page it cites. A quote that is not there is flagged for the
coordinator, and a finding with no quote that checks out is marked unsupported.

Step 4 covers what step 3 can't: a misread page. The quotes a decision rests on, and any
quote with a number in it, are looked for again on the original page image.
"""

import base64
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

import anthropic

from common import MODEL, criteria_prompt, fingerprint, packet_dir, rule_index
from read_pages import _upload_bytes, read_packet

STATUSES = ["ok", "problem", "arrange", "coordinator_call", "cant_tell", "missing"]

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
                "decision": {"type": "string", "enum": ["approve", "approve_once_arranged", "deny", "need_more_info"]},
                "lean_if_forced": {"type": "string", "enum": ["approve", "deny"]},
                "why": {"type": "string"},
                "deciding_rule_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["decision", "lean_if_forced", "why", "deciding_rule_ids"],
            "additionalProperties": False,
        },
        "arrange_first": {"type": "array", "items": {"type": "string"}},
        "ask_hospital": {"type": "array", "items": {"type": "string"}},
        "reply_draft": {"type": "string"},
    },
    "required": ["summary", "reason_for_hospital_stay", "findings", "conflicts", "suggestion",
                 "arrange_first", "ask_hospital", "reply_draft"],
    "additionalProperties": False,
}

REVIEW_INSTRUCTIONS = """You are helping an Illumination Health + Home (IHH) referral coordinator review one hospital referral packet against IHH's admission rules (in the system prompt). The coordinator makes the decision. Your job is to show them, rule by rule, what the packet says, with the page number and the exact words, so they can check you in seconds.

The packet is above as page transcripts, made from faxed page images. It is a real referral with identifiers blacked out.

How to read it
- Check the chart, not only the referral form. The form is one person's summary and can be wrong; the deciding fact is often deep in the chart. When the form and the chart (or two chart pages) disagree, the chart wins: report the conflict, and judge the rule on the chart.
- Never mark a rule ok on the referral form alone when the rule is about the patient's condition or abilities. If only the form supports it, use cant_tell and say the chart doesn't confirm it.
- What the packet does not say is unknown, not normal. Use cant_tell. An unknown never counts against the patient: IHH's process is that the coordinator contacts the hospital for anything missing. Put it on ask_hospital.
- [redacted] marks a privacy redaction, not a missing document. Dates are redacted, so any rule that turns on a date or a number of hours is cant_tell; say "dates removed for privacy".
- When the outline and the referral form disagree, the outline wins (see "Which document wins"). Where the written rules are unclear (see the last section of the rules), say so in the explanation instead of guessing.
- Registered sex offender status is never a problem on its own: it is case by case. Report it as coordinator_call.
- Some packets have no IHH referral form. That is a missing document, not a reason to stop.

Which rules to report
- One finding for the general criteria: the GEN rule the packet best supports.
- Every rule of kind must or exclude in the main rule list (ADL, MOB, MH, COG, OTH, INF and the rest), and every DOC item in the referral checklist.
- Every rule for a specific condition, treatment or device this patient has (for example the diabetes rules for a diabetic, IV rules for a patient with a PICC line, wound rules for a wound, cardiac rules after a heart procedure).
- Skip rules that plainly do not apply to this patient. Do not report FORM rules that a main-list rule already covers.

Statuses
- ok: the packet shows the rule is met. For a document item: the document is in the packet.
- problem: the packet shows something that rules the patient out under a must or exclude rule. Only use it when the chart shows the fact; never for something unknown, unconfirmed or not yet arranged.
- arrange: a rule that allows the patient if something is arranged before admission (rules of kind conditional, and condition rules that say a service must be ordered, coordinated or scheduled, such as home health for IV access or wound care, oxygen delivery, hospice, dialysis schedule, follow-up appointments), and the packet doesn't show it arranged yet. This is not a reason to deny: it is something the hospital sets up first. Say exactly what must be arranged.
- cant_tell: the packet does not settle it.
- coordinator_call: the packet shows something that matters, but IHH's written rules don't settle it and a person has to judge. Use it for case-by-case rules, for the unclear places listed at the end of the rules, and for facts that come close to a rule without matching its wording. Explain what the coordinator has to weigh.
- missing: a document item the hospital was asked to send is not in the packet.

Evidence
- Give at least one quote for every ok, problem, arrange and coordinator_call finding, and for a conflict give one quote per side.
- Each quote must be copied character for character from the transcript of the page you cite, 4 to 30 words, one passage per quote. It will be checked automatically against that page; a quote that is not on the page is flagged as unreliable. Never paraphrase inside a quote and never combine words from two places.
- Use the page numbers from the "=== Page N" headers.

Headline: a few plain words a coordinator can scan, e.g. "Walks 150 ft with a walker". Explanation: one or two sentences.

Suggestion
- deny: only when at least one problem finding shows the chart rules the patient out under IHH's written rules. Unknowns, missing documents and things not yet arranged are never reasons to deny.
- approve_once_arranged: nothing rules the patient out, and one or more arrange findings must be set up before admission. List them in arrange_first.
- approve: nothing rules the patient out and nothing needs arranging.
- A missing date alone never makes a packet need_more_info: dates are removed for privacy in every packet. Judge on what the packet can show.
- need_more_info: only when a single missing fact would decide between approve and deny, for example the chart hints at one of IHH's written exclusions without settling it, and only the hospital can confirm it. Ordinary gaps (swabs, notes, vitals, dates) are not enough: approve and ask for them.
- lean_if_forced: deny only if a problem finding rules the patient out; otherwise approve.
- why: two sentences at most, naming the rule IDs that decide it.

arrange_first: what the hospital must set up before admission (from the arrange findings). Empty if nothing.

ask_hospital: short items the coordinator would request from the hospital case manager. Empty if nothing is needed.

reply_draft: a short message from the coordinator to the hospital case manager, 120 words at most. Refer to "the patient", never a name. Match the suggestion: for approve, say what is still needed before transport; for approve_once_arranged, say the patient can be accepted once the listed items are arranged; for deny, a brief reason as IHH's form promises; for need_more_info, the list of what to send. It is a draft the coordinator will edit and send themselves."""


def _client():
    return anthropic.Anthropic(max_retries=8, timeout=anthropic.Timeout(600, connect=30))


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


# Words that flip a clinical meaning. A near match may never differ on one of these.
POLARITY = {"no", "not", "yes", "denies", "denied", "deny", "negative", "positive", "neg", "pos", "without",
            "with", "none", "never", "unable", "able", "independent", "dependent", "assist", "assistance",
            "x", "normal", "abnormal", "absent", "present", "is", "isn"}


def _match(quote_words, page_words):
    """Best match of the quote in the page: (score, window). 1.0 is word for word."""
    n = len(quote_words)
    if not n or not page_words:
        return 0.0, []
    if " ".join(quote_words) in " ".join(page_words):
        return 1.0, quote_words
    vocab = set(page_words)
    if sum(w in vocab for w in quote_words) / n < 0.6:
        return 0.0, []
    # Only try windows that start near one of the quote's first words.
    starts = set(quote_words[:3])
    best, best_window = 0.0, []
    for i, word in enumerate(page_words):
        if word not in starts:
            continue
        for start in range(max(0, i - 2), i + 1):
            for length in (n - 1, n, n + 1):
                window = page_words[start:start + length]
                r = SequenceMatcher(None, quote_words, window, autojunk=False).ratio()
                if r > best:
                    best, best_window = r, window
        if best > 0.97:
            break
    return best, best_window


def _meaning_changed(quote_words, window):
    """True if the words that differ include a number or a word that flips the meaning."""
    sm = SequenceMatcher(None, quote_words, window, autojunk=False)
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal":
            continue
        for w in quote_words[a1:a2] + window[b1:b2]:
            if w in POLARITY or any(ch.isdigit() for ch in w):
                return True
    return False


def check_quote(evidence, page_words):
    """Label one quote: on_page, close (small transcription differences), other_page or not_found."""
    qw = _words(evidence["quote"])

    def near(words):
        score, window = _match(qw, words)
        return score >= 0.8 and not _meaning_changed(qw, window)

    cited = page_words.get(evidence["page"], [])
    if _match(qw, cited)[0] >= 0.999:
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
    kinds = {p["page"]: p["kind"] for p in read["pages"]}
    for f in review["findings"]:
        good = [e for e in f["evidence"] if e["check"] in ("on_page", "close")]
        f["supported"] = bool(good) or f["status"] in ("cant_tell", "missing")
        # The referral form is one person's summary. A pass resting on it alone is not a pass.
        f["form_only"] = (f["status"] == "ok" and not f["rule_id"].startswith("DOC") and bool(good)
                          and all(kinds.get(e["page"]) == "ihh_referral_form" for e in good))
    return counts


# ------------------------------------------------------------ image check

IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "seen": {"type": "string", "enum": ["yes", "no", "unclear"]},
                    "page_says": {"type": "string"},
                    "box": {
                        "type": "object",
                        "properties": {k: {"type": "integer"} for k in ("x0", "y0", "x1", "y1")},
                        "required": ["x0", "y0", "x1", "y1"],
                        "additionalProperties": False,
                    },
                },
                "required": ["n", "seen", "page_says", "box"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def _check_page_image(client, image, quotes):
    width, height = _png_size(image)
    listing = "\n".join(f"{i}. {q}" for i, q in enumerate(quotes, 1))
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                     "data": base64.standard_b64encode(_upload_bytes(image)).decode()}},
        {"type": "text", "text": (
            "This is one page of a faxed, de-identified hospital record. Black boxes are privacy redactions.\n"
            "For each numbered passage below, look at the image and say whether the page really shows it, "
            "with the same meaning and the same numbers, doses and yes/no marks. Small spelling or spacing "
            "differences are fine. Answer yes, no, or unclear (unreadable). In page_says, give what the page "
            "actually shows at that spot, in a few words, without copying any identifier. In box, give the "
            f"rectangle around the passage in pixels of this image, which is {width} wide and {height} tall: "
            "x0,y0 top-left and x1,y1 bottom-right. If you can't find it, give all zeros.\n\n" + listing)},
    ]
    with client.messages.stream(
        model=MODEL, max_tokens=8000, thinking={"type": "adaptive"},
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": IMAGE_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason in ("refusal", "max_tokens"):
        return {}
    text = next(b.text for b in message.content if b.type == "text")
    items = {it["n"]: it for it in json.loads(text)["items"]}
    for it in items.values():
        b = it.pop("box")
        if b["x1"] > b["x0"] and b["y1"] > b["y0"]:
            # Fractions of the page, so the viewer can draw the box at any size.
            it["box"] = [round(min(max(v / d, 0), 1), 4) for v, d in
                         ((b["x0"], width), (b["y0"], height), (b["x1"], width), (b["y1"], height))]
    return items


def image_check(packet_id, review):
    """Look at the page image itself for the quotes that matter most.

    The text check only proves a quote matches what Claude read. This one asks Claude to
    find each quote again on the original page image, one page at a time, and say where it is
    so the viewer can mark the spot.
    """
    from read_pages import render_pages
    images = render_pages(packet_id)
    by_page = {}
    for item in review["findings"] + review["conflicts"]:
        for ev in item["evidence"]:
            if 1 <= ev["page"] <= len(images):
                by_page.setdefault(ev["page"], []).append(ev)
    client = _client()
    with ThreadPoolExecutor(3) as pool:
        futures = {pool.submit(_check_page_image, client, images[page - 1], [e["quote"] for e in evs]): evs
                   for page, evs in by_page.items()}
        for future, evs in futures.items():
            try:
                answers = future.result()
            except anthropic.APIError:
                answers = {}
            for i, ev in enumerate(evs, 1):
                a = answers.get(i)
                ev["image_check"] = a["seen"] if a else "unclear"
                if a and a["seen"] != "yes":
                    ev["image_says"] = a["page_says"]
                if a and a.get("box"):
                    ev["box"] = a["box"]
    checked = [ev for evs in by_page.values() for ev in evs]
    return {"checked": len(checked), "seen": sum(ev["image_check"] == "yes" for ev in checked),
            "not_seen": sum(ev["image_check"] == "no" for ev in checked)}


# ------------------------------------------------------------------- run

def review_packet(packet_id, progress=lambda text: None, fresh=False):
    out = packet_dir(packet_id) / "review.json"
    if out.exists() and not fresh:
        return json.loads(out.read_text())

    started = time.time()
    status = packet_dir(packet_id) / "status.json"
    shown = progress

    def progress(text):  # noqa: F811  also visible to the app when run from a terminal
        status.write_text(json.dumps({"step": text, "at": time.time()}))
        shown(text)

    read = read_packet(packet_id, progress)
    progress(f"Checking {read['page_count']} page{'' if read['page_count'] == 1 else 's'} against IHH's rules")
    review, usage, review_seconds = ask_claude(read)
    progress("Checking every quote against its page")
    counts = check_review(review, read)
    progress("Looking for the key quotes on the page images")
    counts["image"] = image_check(packet_id, review)

    rules = rule_index()
    for f in review["findings"]:
        rule = rules.get(f["rule_id"])
        f["rule_text"] = rule["text"] if rule else None
        f["rule_section"] = rule["section"] if rule else None
        f["known_rule"] = rule is not None

    result = {
        "packet_id": packet_id,
        "sha256": read["sha256"],
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
    status.unlink(missing_ok=True)
    return result


def recheck(packet_id, images=True):
    """Re-run the quote checks on a saved review without asking for a new review."""
    out = packet_dir(packet_id) / "review.json"
    result = json.loads(out.read_text())
    read = read_packet(packet_id)  # verifies the file's fingerprint first
    result["sha256"] = read["sha256"]
    review = result["review"]
    for item in review["findings"] + review["conflicts"]:
        for ev in item["evidence"]:
            for k in ("check", "found_on", "bad_page", "image_check", "image_says", "box"):
                ev.pop(k, None)
    counts = check_review(review, read)
    if images:
        counts["image"] = image_check(packet_id, review)
    result["quote_check"] = counts
    out.write_text(json.dumps(result, indent=1))
    return counts


if __name__ == "__main__":
    import sys
    from common import load_env
    load_env()
    if "--recheck" in sys.argv:
        print(json.dumps(recheck(sys.argv[1]), indent=1))
        sys.exit()
    r = review_packet(sys.argv[1], progress=print, fresh="--fresh" in sys.argv)
    s = r["review"]["suggestion"]
    print(json.dumps({"decision": s["decision"], "lean": s["lean_if_forced"], "why": s["why"],
                      "quote_check": r["quote_check"], "seconds": r["seconds"]}, indent=1))
