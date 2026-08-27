# Project: Multi-Client Data Validation & AI Insight Tool

## Business context
AGL runs retail crawl data for multiple CPG clients across platforms (Amazon, quick-commerce apps, etc.). The data goes through a raw stage and a processed stage. I need a tool that validates this data using fixed rule-based checks, then uses an AI layer to turn the validation results into a readable report. This is a separate standalone tool — it does not get built into any existing dashboard.

## Known validation rules (confirmed, from a Nestle example)
- Price rule: `MRP >= SP` always
- OSA derivation:
  - `osa_remark=0` → Out of stock → `osa=0`
  - `osa_remark=2` → Not listed → `osa=0`
  - `osa=1` (in stock) requires: price fields not zero, title not blank/'0', `price_rp >= price_sp`
- Completeness check: expected row count = SKUs × locations (e.g. 100 SKUs × 10 locations = 1,000 expected rows)
- Data hygiene: strip dummy rollup rows like `region = 'All'`
- Platform ID convention: sub-platforms share a base product ID with a prefix (e.g. Amazon → `AN-` = Amazon Now, `AF-` = Amazon Fresh)
- Schema hints: client-specific table `ebux_offtake.nestle_location_master`; shared crawl table `ebux_pdp`, filtered by `pf_id` (platform id)

## Scope for this build
Build and prove the full pipeline against **one client first: Nestle** (the example above), since that's the one with a confirmed rule set. Design every check as a parametrized function/query that takes a client identifier as input, not hardcoded to Nestle, so extending to additional clients later is a configuration change, not a rewrite. Don't attempt to onboard every client in this pass.

## Report output
This must be its own separate, standalone tool, not added to any existing dashboard. Use whatever the simplest, lowest-effort option is to get a working prototype — a lightweight local Streamlit app is my default assumption for this, since it needs no deployment infrastructure, but tell me if you think something even simpler fits better (e.g. a generated static HTML/PDF report) given what the output actually needs to show.

## What the finished tool should do
1. Pull data for the target client/platform from the shared table, using its status flag to distinguish raw vs. processed records
2. Run all rule-based validation checks in real code (SQL/Python), never estimated by an LLM
3. Store pass/fail results per rule, per row/record
4. Feed only the validation *results* (not raw data) to an LLM to generate a plain-language summary report — what failed, how much, any patterns worth flagging
5. Display the report in the chosen output format

## Constraints and preferences
- **Free stack only** — this is a prototype/internal tool, not production. Use free-tier or fully open-source/local tools (e.g. the Gemini API free tier for the AI narration layer, since it's genuinely free with no card needed). Don't reach for paid services.
- Database: DuckDB for the MVP — no server to stand up.
- All arithmetic and rule logic must run in actual code/queries, never guessed by the LLM. The LLM's only job is narrating already-computed results.
- Log every validation run and its results for auditability.
- I'm a beginner developer (intern), so favor the simplest architecture that actually works over a maximally scalable one.

## Confirmed rule set and schema details
- **This is the complete rule set** — there are no additional validation rules beyond the ones listed above.
- **Raw and processed data live in the same table**, distinguished by a status flag column. Don't assume the exact column name or values — confirm those once you inspect the real table.
- **Full active platform (`pf_id`) list for Nestle** (only currently-active platforms shown; a handful of other rows in the source file are inactive or look like placeholder/test entries and can be ignored):

| pf_id | Platform | Alias | PDP table |
|---|---|---|---|
| 1 | Flipkart National | FK | flipkart_crawl_pdp |
| 2 | Amazon FBA | AMZ | amazon_crawl_pdp |
| 3 | Flipkart Supermart | FKSM | flipkart_supermart_crawl_pdp |
| 4 | Bigbasket | BB | bigbasket_crawl_pdp |
| 6 | Blinkit | GR | grofers_crawl_pdp |
| 7 | Amazon Fresh Ambient | AMZ_FRESH | amazon_fresh_crawl_pdp |
| 10 | 1MG | OMG | 1mg_crawl_pdp |
| 17 | Swiggy Instamart | SWG | swiggy_instamart_crawl_pdp |
| 20 | Amazon Fresh Chilled | AMZ_FRESH | amazon_fresh_chocolate_crawl_pdp |
| 29 | Zepto | ZEP | zepto_crawl_pdp |
| 32 | First Cry | FC | firstcry_crawl_pdp |
| 35 | Flipkart Minutes | FKM | flipkart_minutes_crawl_pdp |
| 38 | Supertails | SPT | supertails_crawl_pdp |
| 53 | Amazon Now | ANW | amazon_now_crawl_pdp |

The full source file will be in the project folder — double check against it directly rather than retyping this table if precision matters.

## What I need from you right now
Don't write any code yet. First:
1. Give me a full implementation plan broken into clear phases (e.g. schema mapping, validation engine, AI narration layer, output, testing).
2. For each phase, list concrete deliverables and the exact free/open-source libraries or free-tier services you'd use.
3. Research and apply standard conventions for things like data validation testing patterns yourself — don't ask me about things you can reasonably look up or infer from the context given.
4. Ask me anything else that's genuinely specific to my company's data and isn't already covered above.

Wait for me to confirm the plan before writing any code.
