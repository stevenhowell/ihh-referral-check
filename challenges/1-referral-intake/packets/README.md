# Real referral packets (de-identified)

Eleven referral packets that Illumination Health + Home actually received and decided, shared by
IHH for this event. 282 pages in all.

**De-identified to the HIPAA Safe Harbor standard.** Every name (patient, family, clinicians,
staff), every date with a month or day, every facility other than IHH, every address, phone,
fax, email, record or account number, signature, barcode and photo is blacked out. Everything
clinical is left as it arrived. The redaction is burned into the page images; there is no text
layer underneath.

Rules for these files:

- **Do not copy them into your team's repository** or post them anywhere. Point your code at this
  folder.
- **If you see a name, date, number or anything else that identifies someone, stop and tell an
  organizer.** Do not copy it, search it or try to work out who anyone is.

| Packet | Pages | What is in it |
|---|---|---|
| R01 | 34 | Fax cover; IHH referral form; health plan (CalAIM) authorization form, pages out of order; face sheet; 19 pages of sideways medication records; PT evaluation (upside down); progress-note fragments |
| R02 | 22 | Fax cover; face sheet; IHH referral form; CalAIM authorization form; nursing note; labs; imaging; medication list; history and physical |
| R03 | 23 | Fax cover; health plan authorization request; face sheet; PT evaluation; history and physical; labs; imaging; cardiac catheterization report; ECG |
| R04 | 18 | Face sheet; IHH referral form; health plan forms; history and physical; labs; medication record; an older record scanned sideways |
| R05 | 14 | IHH referral form; face sheet; CalAIM authorization form; history and physical; nursing flowsheets; medication record |
| R06 | 30 | Fax cover; face sheets; medication list; history and physical; labs; imaging; progress notes; IHH referral form last |
| R07 | 30 | Fax cover; IHH referral form; face sheet; history and physical; OT and PT evaluations; ten pages of progress notes; social work notes |
| R08 | 29 | IHH referral form; CalAIM authorization form; history and physical; face sheet; PT evaluation; nursing notes; physician orders; labs |
| R09 | 30 | Fax cover; face sheets (twice); medication list; history and physical; labs; progress and social work notes; OT and PT evaluations; IHH referral form last |
| R10 | 21 | Fax cover; face sheet; history and physical; PT evaluation; psychiatry consult; progress notes; medication record. No IHH referral form |
| R11 | 31 | Fax cover; IHH referral form; CalAIM authorization form; face sheet; wound and progress notes; consult and social work notes; labs and vitals scanned sideways |

The PDFs are not in git. [Download them from Google Drive](https://drive.google.com/drive/folders/1ISmUtoNCTW3NJNqCQJHJzb6C319RgrXM) (**Download all**), unzip, and move
the 11 PDFs straight into this folder as `R01.pdf` to `R11.pdf`. Git ignores them here. Image-only pages at 200 dpi, as a coordinator receives them.

## What IHH decided

[`../eval/decisions.json`](../eval/decisions.json) has IHH's real decision for each packet: approved or denied.
**Keep it out of your tool's sight** while it reviews a packet.

What it does not have: the reason. IHH's staff-only section on the referral form is blank in every
packet, so no denial reason is written down. Working out *why*, from the chart and the criteria, is
the coordinator's job, and a good tool shows its reasoning. IHH staff in the room can tell you
whether your tool got it right.

## Things to know

- **Dates are blacked out.** Rules that turn on hours (24 hours on insulin, 72 hours after alcohol,
  a COVID swab within 24 hours) often cannot be checked here. Times of day without a date are left.
  Your tool should say "can't tell from this packet", not guess.
- **Real packets are messy.** Pages out of order, sideways or upside down, near-blank, duplicated,
  or from an earlier stay. Some packets have no IHH referral form at all.
- **Charts disagree with themselves.** Ages, eyes, living situations and medication plans
  sometimes differ from one page to the next. That is the job.
- **Black boxes are not findings.** A blacked-out field means "removed for privacy", not "missing
  from the packet". Do not report a redacted name or date as a missing document.
