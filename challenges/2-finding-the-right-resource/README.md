# Challenge 2: Finding the right resource

> How might we help someone getting back on their feet find the right next door, and walk through
> it?

**Who it's for.** An IHH client getting ready to leave recuperative care, with practical questions:
where do I sleep, who can help me find work, can I get a small loan, can anyone help me get home to
family?

**Today.** Orange County has programs for most of these. Finding the one that fits, working out
whether you qualify and making the first call is where people get stuck. For some needs, like help
getting home to family, there is almost nothing public.

**If you crack it.** A person who leaves knowing exactly what to do today, in plain words, in their
language.

In IHH's words, clients "can struggle searching for and accessing community resources to suit their
specific needs." This is about IHH's clients and those four needs, not a general Orange County
directory.

## Guardrails

Never invent a service fact. Your tool sends nothing. If someone says they are in danger, give the hotline and bring in staff, and never
show the address of a domestic violence shelter.

## What's in this folder

| Path | What it is |
|---|---|
| [`data/oc-resources.seed.json`](data/oc-resources.seed.json) | A starter list built around the four needs IHH named, plus a few extras. Every entry has a source link and the date it was checked |
| [`data/DATA-SOURCES.md`](data/DATA-SOURCES.md) | Larger directories you can pull from, with their terms of use |
| [`scenarios/client-scenarios.json`](scenarios/client-scenarios.json) | 12 made-up client situations |

The starter list is a starting point, not a source of truth. Programs close and numbers change.
Shelter and work are well covered by public sources. Small loans and travel home to family are thin,
and how IHH handles them today is an open question.

Made-up clients only. See the [ground rules](../../docs/ground-rules.md).
