# CLAUDE.md

You are working with a team at a one-day hackathon, the Orange County Claude Impact Lab. The team
is building a prototype for Illumination Health + Home (IHH), a nonprofit that provides housing,
healthcare and case management for people experiencing homelessness. Teams mix engineers,
designers, and healthcare and nonprofit people. Some have never used a terminal.

## Rules that do not bend

- **No identifiable patient information.** `challenges/1-referral-intake/packets/` holds real
  referral packets with every identifier blacked out: read them, but never copy them into a team
  repo and never try to identify anyone. If a page shows an identifier that was missed, stop and tell
  the user to find an organizer. Everything else is invented or public. If someone gives you text, a file or a screenshot that looks like a
  real person's health or personal information, stop. Say what you noticed. Do not process, summarize, save or commit it. Tell them to find an
  organizer.
- **Prototype only.** Do not write code that connects to, reads from or writes to any IHH system,
  or that sends email, text messages or faxes to real people or services.
- **Quality control.** AI makes mistakes. Build in a way to catch them. How is up to you.
- **Never invent facts about a service or a patient.** No made-up phone numbers, addresses, hours,
  eligibility rules, lab values, page numbers or quotes. If the source does not say, the answer is
  "unknown".
- **No medical, legal or immigration advice** in anything client-facing. Point to staff.
- **No secrets in git.** API keys go in environment variables. `.env` is ignored.

## Where things are

- `docs/ground-rules.md`: the event rules in full.
- `docs/background.md`, `docs/glossary.md`: what recuperative care is and what the terms mean.
- `challenges/1-referral-intake/`: admission criteria as markdown and JSON with rule IDs,
  eleven real de-identified referral packets (`packets/R01.pdf` to `R11.pdf`, image-only faxes,
  not in git: if missing, tell the team to download them from https://drive.google.com/drive/folders/1ISmUtoNCTW3NJNqCQJHJzb6C319RgrXM), and IHH's decision on
  each (`eval/decisions.json`).
- `challenges/2-finding-the-right-resource/`: a sourced seed directory built around the four needs
  IHH named (shelter, work, microloans, travel home), a guide to larger data sources, and twelve
  client scenarios. The challenge is about IHH clients leaving care, not a general OC directory.
- `challenges/3-staff-ai-confidence/`: role cards.
- `templates/TEAM-README.md`: what the team's README must cover before they submit.

## How to work today

- The team has about seven hours. Help them build what they decide.
- When the written criteria are unclear or two sources disagree, show that to the user. Do not
  pick silently.
- Say "unknown" when it is unknown. A confident wrong answer is the worst outcome here.
- Keep the team's README current as you go. Submissions are due at 4:00 PM.
- Commit often with clear messages. The team's own work starts after 9:30 AM on the day.

## Challenge 1 specifics

- Rule IDs come from `challenges/1-referral-intake/criteria/admission-criteria.json`.
- Check the chart, not only the referral form. The form is one person's summary and can be wrong.
- A result that is not in the packet is `unknown`, not normal.
- When reviewing a packet, do not read `challenges/1-referral-intake/eval/decisions.json`. It
  exists for checking, not for reviewing.
- Dates are blacked out. A rule that needs a date or a count of hours is "can't tell". A black box
  is "removed for privacy", not a missing document.
