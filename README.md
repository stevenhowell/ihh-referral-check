# Fetch

> For IHH's referral coordinators: Fetch reads a faxed hospital referral, checks it against IHH's admission rules, and hands the coordinator a worklist where every finding points to the page and the exact words it came from.

**F**inds the evidence · **T**races it to the page · **C**hecks it twice · **H**ands it to the coordinator

**Team:** Fetch
**Members:** Steven Howell
**Challenge:** 1 Referral intake
**Built at:** Orange County | Claude Impact Lab, October 17, 2026, with Illumination Health + Home

## The problem

A referral coordinator gets 15 to 35 faxed pages per referral, crooked and handwritten in places, and has to read them against six pages of admission criteria. IHH promises hospitals an answer within two hours, and a slow answer can mean a patient leaves the hospital for the street. The fact that decides the case is often deep in the chart and contradicts the referral form on page 2.

## What we built

A coordinator's desk in the browser:

- **Queue.** Referrals oldest first, with time waiting against the 2-hour target, Fetch's suggestion, and the number of open risks. A dashboard shows what's left to review, what Fetch suggests approving or denying, what has risks to look at, and beds available (typed in by a person).
- **One referral, top to bottom.** A one-line client summary and what Fetch suggests, then **Flagged for the coordinator**: anything that rules the patient out, needs a person's judgment, must be arranged first (home health for IV antibiotics, wound care), or where the pages contradict each other. Then the client profile, a "Before you say yes" checklist, and every IHH rule group, each opening to the rule-by-rule result and reason.
- **Every claim shows its source.** Each finding and profile fact has a page button. It opens the original fax page with a box drawn around the quoted words.
- **Decide, then next.** Approve or Deny with your initials and an optional reason; Fetch records the time from opening to decision and opens the next referral. When the queue is empty it says so.
- **Export PDF.** A record of the decision, who made it and when, Fetch's suggestion (labeled as a suggestion), every flagged item with page and quote, every rule checked, a log of every change, and the fax's SHA-256.
- **Tasks.** Every flagged risk becomes a task with a suggested reviewer (coordinator, LVN, clinical lead, program manager) that anyone can reassign and mark done.

**Live:** [fetch.stevenluishowell.com](https://fetch.stevenluishowell.com), the landing page (also at [stevenhowell.github.io/ihh-referral-check](https://stevenhowell.github.io/ihh-referral-check)). The app itself runs on a laptop, below. The page is served by the small Worker in `site/`.

**Demo video:** to be added

## How Claude is used

When it runs, Fetch makes these calls to Claude (Opus 5.5):

1. **Read.** Each fax page is sent as an image, a few pages at a time, labeled with its page number. Claude transcribes it word for word, marks checkboxes, writes `[redacted]` for black boxes and `[illegible]` for anything it can't read. Pages scanned sideways are turned upright and read again at higher resolution.
2. **Review.** The transcripts and IHH's rules (with their rule IDs) go to Claude, which returns a finding per rule with the page and exact quote, plus contradictions between pages and a suggestion.
3. **Check the quotes against the page image.** Claude looks at the original page image and confirms each quote is really there, and where.
4. **Profile.** A client profile is built from the transcripts, every fact with its page and quote.

Quality control that does not use AI:

- **Quote check in code.** Every quote is matched against the transcript of the page it cites. A near match never excuses a changed number or a flipped word ("denies" vs "reports", "with" vs "without").
- **Timing guard in code.** IHH's dates are blacked out, so rules that depend on a time window (24 hours, 72 hours) can never pass or fail; Fetch shows them as "can't tell" and says why.
- **Form-only flag.** A pass that rests only on the referral form, which is one person's summary, is marked as not confirmed by the chart.
- **File fingerprint.** Each fax's SHA-256 is recorded when it's read. A review is only shown for the exact file it came from; originals are made read only.
- **A person decides.** Fetch's output is always labeled "Fetch suggests". Only a coordinator records a decision.

How it was built: with Claude Code during the event. IHH's real decisions (`eval/decisions.json`) are read only by the Score screen, after a review is finished; the review never sees them.

## Try it

You need macOS (it uses `sips` for images), Python 3.9+, `poppler` for `pdftoppm`, Google Chrome (for PDF export), and a Claude API key.

```bash
brew install poppler
pip3 install -r app/requirements.txt
echo "ANTHROPIC_API_KEY=your-key" > .env
python3 app/server.py
```

Then open http://localhost:8811. Put IHH's packets in `challenges/1-referral-intake/packets/` (see that folder's README), or drop any referral PDF or photo onto the queue. A fresh scan averaged 6 min 42 s per referral across IHH's 11 (3 to 15 minutes, measured three at a time on venue Wi-Fi), at roughly $1 to $2 of API use each.

## What is real and what is mocked

| Part | Status |
|---|---|
| Reading faxed pages, sideways pages upright | Working |
| Rule-by-rule review against IHH's criteria with rule IDs | Working |
| Quote check in code, image check by Claude, timing guard | Working |
| Client profile with page evidence | Working |
| Queue, dashboard, tasks, decisions, PDF export | Working, stored in local files |
| Beds available | Typed in by a person; not connected to anything |
| Who reviews a task | Our suggested defaults by kind of rule; IHH has not confirmed them |
| Connection to IHH's systems or EMR | None, by design. The PDF is a record a person can file |
| Login | None. Initials are typed at decision time |

## How well it works

On IHH's 11 real, de-identified referrals:

- **Matches IHH's decision on 10 of 11.** Runs went 5, 9, 9, then 10 of 11. Two rule changes after the first run came from IHH's own documents: unknown items never count against the patient (IHH asks the hospital for them), and "allowed if arranged" rules mean approve once arranged. The third run added accuracy fixes from an independent audit of Fetch's readings, none using IHH's decisions. The last change came from studying a disagreement with IHH: a value can't rule a patient out when another reading of the same measurement is blacked out, or when the diagnosis behind the rule isn't confirmed. Because changes came after seeing results, a referral Fetch hasn't seen is the fairest test.
- **The four denials:** on each, Fetch flagged at least one of the same rules a separate after-the-fact reading identified as the likely reason.
- **Independent audit of 656 claims** (an earlier version, before the accuracy fixes): 88.9% correct, 10.4% partly right, 0.8% wrong. No quote was invented; every quote was on the page it cited.
- **Current version:** 511 quotes across the 11 referrals: 510 found in the page text and 508 seen on the page image. The few that miss either check are marked "check by hand" on screen.

## Where it gets things wrong

- **Sideways and faint numbers.** Most reading errors were on sideways lab and vitals tables. They're now read upright, but a blood pressure on a dense upright page was still misread in one packet. Don't trust a single number without opening its page.
- **Overstatement.** Earlier versions sometimes wrote a suspected condition as confirmed, or stated a referral-form claim as a chart fact. Rules and flags now guard against this; it isn't eliminated.
- **Judgment the written rules don't settle.** IHH's aggression rule names staff and other patients; IHH's cardiac rules don't say what to do when an ejection fraction is a chronic baseline. Fetch flags these as "your call" rather than deciding.
- **One of eleven decisions differs from IHH's.** Fetch leans approve on a psychiatric case IHH denied: the only clinical note contradicts the stability rule, and Fetch should have leaned deny. It's a question for IHH staff and a known weakness.
- **Eleven packets is a small test.** A good score shows Fetch isn't broken, not that it's reliable.

We would not trust it to decide, only to read faster and show its work.

## Next steps

- Confirm with IHH which risks go to which reviewer, and how coordinators treat the rules that are case by case.
- Test on referrals Fetch has never seen, including ones IHH hasn't decided yet.
- Re-read dense number-heavy pages (labs, vitals) at higher resolution, not only sideways ones.
- Sign-in, and a store that several coordinators can share.

## Data and privacy

This project uses only data from the event repo and public sources. It contains no real patient or client information. It does not connect to any Illumination Health + Home system.

The referral packets are never committed: they and everything made from them (page images, transcripts, reviews, profiles, decisions, PDFs) live in `work/` and `challenges/1-referral-intake/packets/`, both ignored by git. Fetch writes `[identifier]` instead of anything that looks like a missed redaction and flags the page; two pages it flagged were checked by a person and showed only IHH's own name and email.

## License

[MIT](LICENSE). The event materials in `docs/` and `challenges/` are from the Orange County Claude Impact Lab repo; IHH's criteria documents remain IHH's.
