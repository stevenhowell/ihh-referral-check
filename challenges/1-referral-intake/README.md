# Challenge 1: Referral intake

> How might we help a coordinator say yes in minutes, so a patient doesn't leave the hospital for
> the street?

**Who it's for.** The referral coordinator, and the patient who is ready to leave the hospital but
too sick to recover outside.

**Today.** Each referral is 15 to 35 faxed pages, read by hand against six pages of criteria.
Hospitals send the same referral to several providers, so a slow answer can mean the person is
discharged with nowhere to go. IHH promises hospitals an answer within two hours.

**If you crack it.** A faster, surer answer. A bed instead of the street, and coordinators spending
their time on people, not pages.

**Get the packets first.** They are too big for this repo. Open the
[packets folder on Google Drive](https://drive.google.com/drive/folders/1ISmUtoNCTW3NJNqCQJHJzb6C319RgrXM), choose **Download all**, unzip, and move the 11 PDFs straight into
`challenges/1-referral-intake/packets/`, so you have `packets/R01.pdf` to `packets/R11.pdf`. Git ignores them there.

## The work is done by hand

Open `packets/R01.pdf` ([on Drive](https://drive.google.com/drive/folders/1ISmUtoNCTW3NJNqCQJHJzb6C319RgrXM)) and scroll. That is one referral: 34 pages of faxed scans,
crooked, handwritten in places. The 11 packets here total 282 pages. A coordinator reads every one,
finds the note deep in the chart that contradicts the form on page 2, checks it against the criteria
and writes back to the hospital. Then the next fax arrives.

These are real referrals IHH received and decided, with every name, date, facility, number,
signature and barcode blacked out. A black box means "removed for privacy", not "missing". Do not
copy the packets into your team's repo. If you spot an identifier we missed, stop and tell an
organizer.

## Guardrail

AI makes mistakes. Build in a way to catch them. How is up to you.

## Why it's hard

- The referral form is one person's summary. The fact that decides the case is often deep in the
  chart.
- "Not in the packet" means unknown, not normal.
- IHH's two rule documents don't always agree. The internal admission criteria win over the
  referral form, and some cases fall in gaps between them.

## What's in this folder

| Path | What it is |
|---|---|
| [`packets/`](packets/) | Where the 11 de-identified packets go once you [download them](https://drive.google.com/drive/folders/1ISmUtoNCTW3NJNqCQJHJzb6C319RgrXM). Image-only PDFs, as a coordinator receives them |
| [`criteria/`](criteria/) | IHH's admission criteria and referral form: the original PDFs, transcribed, and as JSON with rule IDs |
| [`eval/decisions.json`](eval/decisions.json) | IHH's real decision on each packet: 7 approved, 4 denied |

IHH never wrote down the reasons for its decisions.

No real patient information beyond these de-identified packets. See the
[ground rules](../../docs/ground-rules.md).
