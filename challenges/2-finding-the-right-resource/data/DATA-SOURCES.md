# Data sources for "Finding the right resource"

A short guide to the larger Orange County directories and datasets you could pull from on the day, beyond the 40 entries in `oc-resources.seed.json`.

Everything below was checked on 2026-10-13 by fetching the page named. It states only what was seen on that page. "Not stated" means the page did not say, not that the answer is no. Terms can change, so read them yourself before you build on a source.

About the seed file: every `source_quote` was fetched again from its `source_url` and matched word for word on 2026-10-13. The one exception is the CalOptima Health entry, whose site blocks automated requests; that entry is marked medium confidence. Every entry is sourced from the organization's own page or a government page.

## At a glance

| Source | What it covers | API, download or website only | Limits on scraping or reuse seen | URL |
|---|---|---|---|---|
| 211 Orange County (211OC) | Orange County health and human services. Its FAQ says specialists use a database of more than 2,000 government and nonprofit agencies. | Website search only. No public API or download is documented. The results page loads its data from an internal JSON endpoint that is not offered or documented for reuse. | The Terms of Use page had no terms text when fetched. Footer: "© Copyright 2026 Orange County United Way. All Rights Reserved." `robots.txt` sets `Crawl-delay: 10`. Ask before any automated use. | https://211oc.org/get-help/resources/ |
| 211 National Data Platform | National 211 resource data. The portal claims 2 million resources and 96% United States coverage. | Yes, REST APIs: Search, Export, Query, Suggest, Filter. V2 is labeled "in preview". The portal has a sign-up link and offers "a free trial". | "Some features are limited for use by 211 organizations contributing data to the platform." Whether 211OC records are included: not stated. | https://apiportal.211.org/ |
| OC Navigator (OC Health Care Agency) | Mental health, substance use and supportive resources (housing, food, transportation, legal help and more), per the County's 2022 press release. | Website only (a JavaScript app on the Chorus platform). API or download: not stated. | `robots.txt` disallows `/m/ocn/` except a short list of allowed pages. Terms: not stated on the pages fetched. | https://ocnavigator.org/m/ocn |
| findhelp.org | National search for "financial assistance, food pantries, medical care, and other free or reduced-cost help", by location. | Website. An API exists but the terms say it needs "a separate paid subscription agreement". | Explicit. Terms forbid copying "regardless of technique (e.g., screen-scraping, downloading, printing...)" and forbid storing, aggregating or compiling the materials. Do not scrape. | https://www.findhelp.org/ (terms: https://www.findhelp.org/legal/terms) |
| OC Coordinated Entry System (County of Orange) | How CES works, who it serves, FAQs, the Shelter Bed Reservation System, and the two County shelters. | Web pages. The County's list of CES Access Points links to a site that requires a login (it shows a "Log in as guest" option, not tested). | Not stated. | https://ceo.oc.gov/care-coordination/homeless-services/coordinated-entry-system-ces |
| County Pocket Guide Resource Directories | Pocket-sized resource guides for the North, Central and South service planning areas and for transitional aged youth: agencies, shelters, food, legal, veterans, hotlines, with phones and hours. | PDF download, in English, Spanish, Vietnamese, Korean and Traditional Chinese. | Not stated on the page. Dated: file names say "Updated 7.28.2025", while the Central guide's own text says "Updated 5.13.2025". | https://ceo.oc.gov/office-care-coordination/get-help |
| OC HMIS public pages | Aggregate homelessness system data: Housing Inventory Count reports (2020 to 2026), Point in Time count, HUD system performance reports, a quarterly CoC dashboard. | PDFs and Power BI dashboards. No API seen. The public pages show aggregate data only. | Not stated. Latest dashboard listed was Quarter 2 2025. | https://ochmis.org/ |
| SAMHSA FindTreatment.gov | Mental health and substance use treatment facilities nationwide. | Yes. A JSON endpoint answered without an API key (example below). | `robots.txt` allows all. Terms: not verified, because the developer guide page needs JavaScript and could not be read. | https://findtreatment.gov/ |
| HUD Resource Locator and HUD Find Shelter | Resource Locator: a HUD map with "Find Nearest HUD Office" and map search. Find Shelter: "housing, shelter, health care, and clothing resources in communities across the country". | Web apps. API or download: not stated on either page. | Not stated. | https://resources.hud.gov/ and https://www.hud.gov/findshelter |
| BenefitsCal | California's online benefits application portal. The County SSA says CalFresh can be applied for online there. It is not a resource directory. | Website only (a JavaScript app; a plain fetch returned only a loading screen). API: not stated. | Not stated (page content could not be read without a browser). | https://benefitscal.com/ |

### FindTreatment.gov example that worked

```
https://findtreatment.gov/locator/exportsAsJson/v2?sAddr=33.6846,-117.8265&limitType=2&limitValue=8000&pageSize=2&page=1&sort=0
```

It returned `page`, `totalPages`, `recordCount` (41 for this query) and `rows` with `name1`, `street1`, `city`, `state`, `zip`, `phone`, `intake1`, `hotline1`, `website`, `latitude`, `longitude`, `miles`, `services`, `typeFacility`. The meaning of `limitType` and `limitValue` was not confirmed, so read the developer guide at https://findtreatment.gov/devguide in a browser.

## Smaller sources that are easier to use

- **Second Harvest Food Bank pantry list.** A searchable map plus a PDF of partner pantries with hours. The page said "List updated as of 09/14/26". https://feedoc.org/need-food/
- **CAP OC / OC Food Bank.** Links a PDF of TEFAP partner sites (May 2026) and a diaper bank partner list. https://www.capoc.org/oc-food-bank/
- **SBA list of microlenders.** HTML table with a state filter. Filtering to California showed 14 intermediaries; none is headquartered in Orange County, and the table does not list counties served. https://www.sba.gov/loans/microloans/list-of-microlenders/?query-202-m_states_served=CA
- **DHCS "SUD Recovery Treatment Facilities".** State open dataset (ArcGIS Hub) of licensed or certified non-medical alcohol and drug recovery or treatment facilities, listed by county. License terms: not stated on the page text fetched. https://gis.dhcs.ca.gov/datasets/CADHCS::sud-recovery-treatment-facilities/about
- **OC Workforce Solutions events.** Current workshops, hiring events and courses. https://www.ocworkforcesolutions.com/events
- **California LifeLine.** The CPUC page points to a provider search at californialifeline.com (not fetched). https://www.cpuc.ca.gov/consumer-support/financial-assistance-savings-and-discounts/lifeline
- **Open Referral HSDS.** The Human Services Data Specification (version 3.0.1 docs) is a ready-made schema for service directories if you do not want to invent one. https://docs.openreferral.org/en/latest/hsds/overview.html

## What 211OC records look like

Useful for designing your own schema. Each result carries a program name, agency name, taxonomy terms, phone, address, hours, eligibility, application process, required documents, website, coverage area, service languages, fees and a "last verified" date. The public site exposes 316 taxonomy terms in 12 groups (Food, Housing, Health Care, Behavioral Health, Children & Family, Bills & Financial, Legal Assistance, Education, Employment, Transportation, Clothing & Hygiene, Disaster Response). One term is "Coordinated Entry System Access Points", which returned 32 records.

Two gaps matter for this challenge. There is no taxonomy term for small business, microloans or microenterprise, and none for family reunification or long-distance travel. The closest transportation terms are bus passes and gas assistance.

## Traps found while building the seed

Every one of these was observed on 2026-10-13. They are the reason each seed entry has `source_url`, `verified_date`, `confidence` and `notes`.

- **Operators change.** The County and PATH say PATH has run Bridges at Kraemer Place since July 1, 2026. The 211OC record, last verified 2026-02-17, still named the previous operator.
- **An address is not always the service site.** Several 211OC records showed the agency's head office (for example a San Diego address for the VA center in Santa Ana). Never route someone to an address without checking it.
- **Websites die or get taken over.** 211OC lists swcommunitycenter.org for Southwest Community Center; that domain served gambling content. someonecareskitchen.org redirected to an unrelated jobs site. Check links before you show them.
- **Old listings linger.** 211OC still listed Mary's Kitchen at 517 W. Struck Ave in Orange. That address is now The HUB Resource Center, and Mary's Kitchen's own site describes a food rescue in Anaheim.
- **Hours drift.** The County pocket guide lists the NAMI OC WarmLine as 24/7. NAMI's own page says 12:00 PM to 12:00 AM. The HUB Resource Center's hours differ between 211OC and its own site.
- **Phone numbers conflict.** Two different numbers were found for the VA Community Resource and Referral Center, for Yale Navigation Center referrals, and for Costa Mesa's homeless services line.
- **Typos in official material.** The County pocket guide prints the benefits portal as "www.benifitscal.com".
- **Closed doors still signposted.** Family Solutions Collaborative closed its online request form, but its own home page and the County guide still point to it.
- **Most shelters are referral-only.** Many also require ties to one city. A shelter address in your app can send someone to a locked door.
- **Some sites block automated requests.** caloptima.org (HTTP 429), score.org (403), kiva.org (406) and anaheim.net (403) refused plain fetches. costamesaca.gov answered only when browser-like headers were sent.

## Two rules

1. Do not scrape 211OC, OC Navigator or findhelp. If you want 211OC data, ask Orange County United Way; the national 211 API is the documented route.
2. Never generate or "fix" a phone number, address or hours. If a field is unknown, show it as unknown.
