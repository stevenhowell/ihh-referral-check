"""Step 1: turn a faxed packet into page images and a transcript of every page.

The faxes have no text layer, so Claude reads each page image. Pages go in small
batches, in parallel, each one labelled with its page number. The transcripts are
saved, so a packet is only ever read once.
"""

import base64
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

import anthropic

from common import MODEL, packet_dir, packet_path

DPI = 150          # about 1275 x 1650 px per page: legible, and well under the image size cap
PAGES_PER_CALL = 3
PARALLEL_CALLS = 6

PAGE_KINDS = [
    "fax_cover", "ihh_referral_form", "health_plan_authorization", "face_sheet",
    "history_and_physical", "discharge_summary", "progress_note", "nursing_note",
    "medication_record", "labs", "vitals", "imaging", "pt_ot_evaluation",
    "social_work_note", "consult", "physician_orders", "procedure_or_ecg", "other", "blank",
]

READ_SYSTEM = """You transcribe pages of a faxed hospital referral packet for a recuperative care program.

The packet is real and de-identified. Black boxes cover names, dates, facilities, numbers and signatures.

For each page image you are given:
- Transcribe every word you can read, in reading order. If the page is sideways or upside down, read it in its correct orientation and set rotated to true.
- Tables: one row per line, cells separated by " | ".
- Checkboxes and yes/no boxes: write [x] for marked and [ ] for unmarked, next to their label, exactly as marked. Circled answers: write (circled) after the word.
- A black redaction box: write [redacted]. Never guess what is under it.
- Words you cannot read: write [illegible]. Never guess a number, a drug name or a dose.
- If you see something that looks like an identifier the redaction missed (a person's name, a full date, a phone number, an address, a record number), do not copy it. Write [identifier] in its place and set possible_unredacted_identifier to true.

Copy the words; do not summarize, correct or interpret them."""

READ_SCHEMA = {
    "type": "object",
    "properties": {
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer"},
                    "kind": {"type": "string", "enum": PAGE_KINDS},
                    "rotated": {"type": "boolean"},
                    "legibility": {"type": "string", "enum": ["clear", "partly_legible", "mostly_illegible", "blank"]},
                    "transcript": {"type": "string"},
                    "possible_unredacted_identifier": {"type": "boolean"},
                },
                "required": ["page", "kind", "rotated", "legibility", "transcript", "possible_unredacted_identifier"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["pages"],
    "additionalProperties": False,
}


def render_pages(packet_id):
    """Render the PDF to PNGs once. Returns the image paths in page order."""
    out = packet_dir(packet_id) / "pages"
    images = sorted(out.glob("p-*.png"))
    if images:
        return images
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pdftoppm", "-r", str(DPI), "-png", str(packet_path(packet_id)), str(out / "p")],
        check=True,
    )
    return sorted(out.glob("p-*.png"))


def _read_batch(client, images, first_page, total):
    content = []
    for offset, image in enumerate(images):
        number = first_page + offset
        content.append({"type": "text", "text": f"Page {number} of {total}:"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png",
                       "data": base64.standard_b64encode(image.read_bytes()).decode()},
        })
    numbers = ", ".join(str(first_page + i) for i in range(len(images)))
    content.append({"type": "text", "text": f"Transcribe pages {numbers}. Return one entry per page, using the page numbers given."})

    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        system=READ_SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": READ_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined to read pages {numbers}.")
    if message.stop_reason == "max_tokens":
        raise RuntimeError(f"The transcript of pages {numbers} was cut off.")
    text = next(b.text for b in message.content if b.type == "text")
    pages = json.loads(text)["pages"]
    expected = {first_page + i for i in range(len(images))}
    pages = [p for p in pages if p["page"] in expected]
    got = {p["page"] for p in pages}
    for missing in sorted(expected - got):
        pages.append({"page": missing, "kind": "other", "rotated": False, "legibility": "mostly_illegible",
                      "transcript": "[This page was not transcribed. Open the image.]",
                      "possible_unredacted_identifier": False})
    return pages, message.usage


def read_packet(packet_id, progress=lambda text: None):
    """Transcribe every page of a packet. Cached in work/<id>/pages.json."""
    cache = packet_dir(packet_id) / "pages.json"
    if cache.exists():
        return json.loads(cache.read_text())

    progress("Opening the fax")
    images = render_pages(packet_id)
    total = len(images)
    batches = [(images[i:i + PAGES_PER_CALL], i + 1) for i in range(0, total, PAGES_PER_CALL)]

    client = anthropic.Anthropic(max_retries=6)
    done = 0
    pages = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    progress(f"Reading {total} pages")
    with ThreadPoolExecutor(PARALLEL_CALLS) as pool:
        futures = [pool.submit(_read_batch, client, imgs, first, total) for imgs, first in batches]
        for future in futures:
            batch_pages, batch_usage = future.result()
            pages += batch_pages
            usage["input_tokens"] += batch_usage.input_tokens
            usage["output_tokens"] += batch_usage.output_tokens
            done += len(batch_pages)
            progress(f"Read {done} of {total} pages")

    pages.sort(key=lambda p: p["page"])
    result = {"packet_id": packet_id, "page_count": total, "pages": pages, "usage": usage}
    cache.write_text(json.dumps(result, indent=1))
    return result
