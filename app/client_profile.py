"""The client profile: who this patient is, clinically, in one card.

Built from the saved page transcripts, so the fax is not read again. Every fact carries
the page and the exact words it came from, and those quotes go through the same two
checks as the review: the page text, then the page image. Names, dates and other
identifiers are blacked out in the fax and are never filled in.
"""

import json
import time

import anthropic

from common import MODEL, packet_dir
from read_pages import read_packet
from review import _transcript_block, check_quote, _words, image_check

SECTIONS = ["About", "Why they're in hospital", "Getting around and daily care", "Care needs",
            "Mind and mood", "Medicines"]

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "one_line": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "enum": SECTIONS},
                    "facts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "value": {"type": "string"},
                                "evidence": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"page": {"type": "integer"}, "quote": {"type": "string"}},
                                        "required": ["page", "quote"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["label", "value", "evidence"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "facts"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["one_line", "sections"],
    "additionalProperties": False,
}

INSTRUCTIONS = """Build a short client profile from this referral packet for a recuperative care coordinator.

Sections, in this order, with these facts where the packet has them:
- About: age, sex, housing situation, insurance or health plan, preferred language.
- Why they're in hospital: the reason for this stay, main diagnoses, any surgery or procedure.
- Getting around and daily care: walking and transfers, devices (walker, wheelchair), bathing, dressing, toileting, continence.
- Care needs: IV lines or IV medicines, oxygen, wounds and wound care, diabetes and insulin, dialysis, catheters, home health.
- Mind and mood: orientation, memory, mental health diagnoses, substance use, behavior, suicidal thoughts.
- Medicines: the main current medicines, and whether they take their own.

Rules:
- One fact per label, a few plain words, no abbreviations a nurse wouldn't use. Example: label "Walking", value "Walks 150 feet with a walker".
- If the packet doesn't say, the value is "Not in the fax" with no evidence. Never guess.
- If two pages disagree, say so in the value ("Form says no wounds; nurse's note describes a leg wound") and quote both.
- Each quote is copied character for character from the cited page's transcript, 4 to 25 words. It will be checked automatically.
- Use the chart's own words; never turn a suspected or past condition into a confirmed current one.
- A blacked-out field is unknown, never "none".
- Orientation: give the exact count (x2, x3, x4). "Alert and oriented" with no count is "Not stated".
- Describe how they are now, not their function before this stay.
- If only the IHH referral form says something, start the value with "Referral form says:".
- List every pain medicine and IV medicine you find, not only the first.
- Never write a name, a date, a phone number, an address or a record number, even if one appears. Ages are fine; write 90 or older as "90 or older".
- one_line: one sentence a coordinator could say out loud, e.g. "62-year-old man, unhoused, recovering from a leg infection on IV antibiotics."
"""


def build_profile(packet_id, progress=lambda text: None):
    read = read_packet(packet_id)  # verifies the file's fingerprint
    progress("Building the client profile")
    started = time.time()
    with anthropic.Anthropic(max_retries=8, timeout=anthropic.Timeout(600, connect=30)).messages.stream(
        model=MODEL,
        max_tokens=32000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": PROFILE_SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "REFERRAL PACKET\n\n" + _transcript_block(read)},
            {"type": "text", "text": INSTRUCTIONS},
        ]}],
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError("The profile could not be built for this packet.")
    profile = json.loads(next(b.text for b in message.content if b.type == "text"))

    # Same checks as the review: the page text first, then the page image.
    progress("Checking the profile against the pages")
    page_words = {p["page"]: _words(p["transcript"]) for p in read["pages"]}
    facts = [f for s in profile["sections"] for f in s["facts"]]
    for f in facts:
        for ev in f["evidence"]:
            ev.update(check_quote(ev, page_words) if ev["page"] in page_words else {"check": "not_found"})
    image_check(packet_id, {"findings": facts, "conflicts": []})
    kinds = {p["page"]: p["kind"] for p in read["pages"]}
    for f in facts:
        good = [e for e in f["evidence"] if e["check"] in ("on_page", "close") and e.get("image_check", "yes") == "yes"]
        f["checked"] = bool(good) if f["evidence"] else None
        # The referral form is one person's summary; say so when it is the only source.
        f["form_only"] = bool(good) and all(kinds.get(e["page"]) == "ihh_referral_form" for e in good)

    result = {"packet_id": packet_id, "sha256": read["sha256"], "profile": profile,
              "seconds": round(time.time() - started), "built_at": time.strftime("%Y-%m-%d %H:%M")}
    (packet_dir(packet_id) / "profile.json").write_text(json.dumps(result, indent=1))
    return result


if __name__ == "__main__":
    import sys
    from common import load_env
    load_env()
    r = build_profile(sys.argv[1], progress=print)
    print(r["profile"]["one_line"], f"({r['seconds']} s)")
