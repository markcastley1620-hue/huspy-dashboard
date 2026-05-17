# Huspy Market Intel — Data Integrity Layer

## 1. Current State Audit

### 1.1 Listing Data (1,586 records)

| Field | Fill Rate | Issue |
|---|---|---|
| listing_id | 100% | ✅ Unique, no duplicates |
| price_num | 100% | ✅ All valid, no outliers detected |
| community | 100% | ⚠ 25 communities have no Bayut slug (109 listings can't be market-benchmarked) |
| sub_community | 99.9% | ✅ |
| type | 100% | ✅ |
| bedrooms | 86.8% | ❌ 210 listings missing bedrooms — excluded from all benchmarks |
| agent | 80.7% | ❌ 306 unattributed — invisible to agent views |
| dom | 49.2% | ❌ Half the portfolio has no days-on-market |
| promo | 23.6% | ⚠ 375 detected, but only 223/648 sub-community groups were checked. Unknown false-negative rate. |
| tower | 56.1% | ⚠ Missing for 44% of listings |
| listed_date | 49.2% | ❌ Same gap as DOM |
| price_sqft | 100% | ✅ But some are 0 when size_sqft is 0 |

### 1.2 Market Data (2,591 sub-community entries)

| Metric | Value | Issue |
|---|---|---|
| Communities | 71 | ⚠ 25 listing communities have no slug |
| Sub entries (sale) | 1,262 | |
| Sub entries (rent) | 1,329 | |
| Thin comps (<3) | 424 (16%) | ⚠ 312 have only 1 comp — unreliable medians |
| Source: unknown | 1,922 (74%) | ❌ No provenance tracking for most entries |
| Source: tracked scrapes | 669 (26%) | |

### 1.3 Known Systemic Bugs

1. **URL path structure** — Bayut uses nested paths for some communities (dubailand/villanova/amaranta). Only 7 are mapped. Others silently return wrong data.
2. **Type-specific URLs** — `/for-sale/property/` returns apartments. `/for-sale/townhouses/` returns townhouses. Scraper doesn't systematically use type-specific paths.
3. **Promo detection** — Company page doesn't show Signature/Hot badges. Search pages do. No systematic coverage tracking. Don't know which sub-communities were checked.
4. **Community-level data injection** — Was injecting community averages into sub-community entries. Removed, but the scraping gaps that caused it still exist.
5. **Pagination instability** — Bayut's concurrent pagination causes ~7% listing loss. Multi-pass helps but doesn't guarantee completeness.
6. **No validation at ingestion** — Data goes straight from scraper to Supabase. No schema validation, no range checks, no cross-field consistency.

---

## 2. Proposed Schema Contract

### 2.1 `huspy_listings` (canonical listing table)

```
listing_id      TEXT        REQUIRED    UNIQUE
url             TEXT        REQUIRED    Pattern: /property/details-\d+.html
agent           TEXT        NULLABLE    NULL = unattributed (flag, don't hide)
community       TEXT        REQUIRED    Must exist in community_registry
sub_community   TEXT        REQUIRED    NULL = flag as incomplete
type            TEXT        REQUIRED    ENUM: Apartment, Villa, Townhouse, Office, Penthouse, Shop, Residential Floor, Residential Plot, Commercial Floor
bedrooms        INTEGER     REQUIRED    0-10 (0 = Studio). NULL = flag as incomplete
bathrooms       INTEGER     NULLABLE    1-20
size_sqft       INTEGER     NULLABLE    >0 when present
price_num       INTEGER     REQUIRED    >0
price_sqft      INTEGER     COMPUTED    = price_num / size_sqft (NULL when size_sqft = 0)
purpose         TEXT        REQUIRED    ENUM: sale, rent
frequency       TEXT        NULLABLE    ENUM: yearly, monthly, weekly, daily (rent only)
promo           TEXT        NULLABLE    ENUM: Signature, Hot, NULL
promo_verified  BOOLEAN     DEFAULT FALSE   TRUE = checked via search page
dom             INTEGER     NULLABLE    >=0
listed_date     DATE        NULLABLE    Must be <= today
tower           TEXT        NULLABLE
title           TEXT        NULLABLE
off_plan        BOOLEAN     DEFAULT FALSE
verified        BOOLEAN     DEFAULT FALSE
trubroker       BOOLEAN     DEFAULT FALSE
scrape_run_id   TEXT        REQUIRED    Links to scrape_runs table
ingested_at     TIMESTAMP   REQUIRED    Auto-set
```

### 2.2 `market_comps` (market benchmark data)

```
id              SERIAL      PRIMARY KEY
community       TEXT        REQUIRED    Must exist in community_registry
sub_community   TEXT        REQUIRED
purpose         TEXT        REQUIRED    ENUM: sale, rent
type            TEXT        REQUIRED    ENUM: same as listings
bedrooms        INTEGER     REQUIRED    0-10
comp_count      INTEGER     REQUIRED    >0
median_price    INTEGER     REQUIRED    >0
prices          INTEGER[]   REQUIRED    Individual prices, sorted
source_url      TEXT        REQUIRED    Exact Bayut URL scraped
scrape_run_id   TEXT        REQUIRED
scraped_at      TIMESTAMP   REQUIRED
```

### 2.3 `community_registry`

```
name            TEXT        PRIMARY KEY
bayut_slug      TEXT        REQUIRED    e.g. "dubai-marina"
bayut_full_path TEXT        NULLABLE    e.g. "dubailand/villanova" (for nested communities)
parent_community TEXT       NULLABLE    FK to self
has_townhouses  BOOLEAN     Discovered during scraping
has_villas      BOOLEAN     Discovered during scraping
has_apartments  BOOLEAN     Discovered during scraping
last_scraped    TIMESTAMP
```

### 2.4 `scrape_runs`

```
run_id          TEXT        PRIMARY KEY     UUID
run_type        TEXT        ENUM: listings, market_community, market_subcommunity, promo_check, agent_recovery, dom_recovery
started_at      TIMESTAMP
completed_at    TIMESTAMP
status          TEXT        ENUM: running, success, partial, failed
records_scraped INTEGER
records_accepted INTEGER
records_rejected INTEGER
credits_used    INTEGER
notes           TEXT
```

### 2.5 `rejected_listings`

```
id              SERIAL
listing_id      TEXT
scrape_run_id   TEXT
rejection_reason TEXT       e.g. "bedrooms_null", "price_out_of_range", "duplicate_id"
raw_data        JSONB       Original scraped data
rejected_at     TIMESTAMP
```

---

## 3. First 15 Data Quality Rules

### Schema Rules

| # | Rule | Scope | Current Violation Count |
|---|---|---|---|
| R01 | `bedrooms` must not be NULL | All listings | 210 (13.2%) |
| R02 | `price_num` must be > 0 | All listings | 0 |
| R03 | `type` must be in allowed ENUM | All listings | 0 |
| R04 | `purpose` must be "sale" or "rent" | All listings | 0 |
| R05 | `listing_id` must be unique per snapshot | All listings | 0 (fixed) |

### Range Rules

| # | Rule | Scope | Current Violation Count |
|---|---|---|---|
| R06 | Sale price: 100K–200M AED | Sale listings | 0 |
| R07 | Rent price: 5K–50M AED/yr | Rent listings | 0 |
| R08 | `size_sqft`: 100–100,000 when present | All listings | TBD |
| R09 | `dom`: 0–730 when present | All listings | TBD |
| R10 | `bedrooms`: 0–10 | All listings | 0 |

### Cross-Field Consistency

| # | Rule | Scope | Current Violation Count |
|---|---|---|---|
| R11 | `price_sqft` must equal `price_num / size_sqft` (±5%) | Where both non-null | TBD |
| R12 | `frequency` must be non-null when `purpose` = "rent" | Rent listings | 691 null (43.6%) — most are valid yearly |
| R13 | `promo_verified` must be TRUE before promo is used in opportunities engine | Opportunities | 0% verified today |

### Cross-Row Consistency

| # | Rule | Scope | Current Violation Count |
|---|---|---|---|
| R14 | Comp median must be within 0.2×–5× of community median for same type+bed | All market_comps | TBD — the Amaranta 6.7M bug would have been caught |
| R15 | Comp count must match actual Bayut page listing count (±20%) | All market_comps | Unknown — no verification exists |

### Rules I'd add next (16–25)

| # | Rule | Description |
|---|---|---|
| R16 | Every sub-community in listings must have a verified Bayut URL path | Prevents wrong-URL scraping |
| R17 | Promo check must cover ALL sub-community groups, not just sampled ones | Prevents false negatives |
| R18 | If comp_count < 3, the benchmark is flagged as "low confidence" in the dashboard | Visual signal |
| R19 | Market data must be refreshed within 48h — stale data gets flagged | Freshness |
| R20 | DOM must be filled for >90% of listings before opportunities engine runs | Gate |
| R21 | Agent must be filled for >95% of listings before agent views render | Gate |
| R22 | No market_comps entry may have source = "community_fallback" or "community_upgrade" | Prevents fake data |
| R23 | Price rank must use same-source data as benchmark (sub-comm prices, not community) | Consistency |
| R24 | Promo changes between snapshots must be logged (added/removed) | Audit trail |
| R25 | Every Bayut URL scraped must be logged with response code and card count | Debug trail |

---

## 4. Migration Plan

### Phase 1: Validation Layer (Day 1)
- Build `validator.py` — single module, all rules as typed classes
- Every rule has: `name`, `check(record) -> pass/fail/reason`, `scope`
- Wrap existing scraper output through validator before save
- Rejected records go to `rejected_listings.json` (file-based first, DB later)
- **Dashboard impact: none.** Same data flows, but now validated.

### Phase 2: Market Data Overhaul (Day 2)
- Build `community_registry.json` with verified Bayut URL paths for all 71 + 25 unmapped communities
- For each community: verify slug, discover nested path, discover available property types
- Replace ad-hoc sub-community scraping with systematic: for every (community, sub_community, type) tuple in listings, scrape the correct Bayut URL
- Store source_url with every market_comps entry — full provenance
- **Dashboard impact: more accurate benchmarks, some opportunities may change.**

### Phase 3: Promo Completeness (Day 2-3)
- Build promo coverage tracker: log which sub-community search pages were checked
- Scrape ALL sub-community groups (648), not just the ones we happened to hit
- Add `promo_verified` field — only verified promos feed into opportunities
- **Dashboard impact: accurate spend data across all agents.**

### Phase 4: Integrity Dashboard (Day 3)
- Separate page: `/integrity` or a new tab
- Shows: rule pass/fail rates, quarantine queue, anomaly feed, scrape coverage, field fill rates
- If any critical rule fails (R01, R13, R14, R15), affected community shows a data quality badge on customer dashboard
- **Dashboard impact: trust signal for management.**

### Phase 5: Scrape Run Tracking (Day 3-4)
- Every scrape gets a `run_id`
- Audit log: run_id, type, records scraped/accepted/rejected, credits used, timestamp
- Re-scrape replaces by run_id, never appends
- Rollback capability: if a run produces bad data, revert to previous run
- **Dashboard impact: none visible, but operational confidence.**

### Phase 6: Anomaly Detection (Day 4-5)
- Per-community: comp count vs 7-day rolling average
- Per-community: median price drift > 15% flags alert
- Cross-community: if any metric is 10× any peer, flag
- Null rate spikes: if a field's null rate jumps >10pp between runs, flag
- **Dashboard impact: anomaly feed on integrity page.**

---

## 5. Timeline

| Day | Deliverable | Customer Dashboard Impact |
|---|---|---|
| Day 1 (Mon) | Validator module + community registry + all R01-R15 rules implemented | None — same data, now validated |
| Day 2 (Tue) | Market data overhaul — systematic scraping with verified URLs + source provenance | More accurate benchmarks |
| Day 3 (Wed) | Promo completeness + integrity dashboard tab | Accurate spend data + trust signal |
| Day 4 (Thu) | Scrape run tracking + rollback capability | None visible |
| Day 5 (Fri) | Anomaly detection + rules R16-R25 | Anomaly alerts on integrity page |

### What doesn't change
- Customer dashboard frontend stays as-is
- Supabase schema stays as-is (integrity layer sits between scraper and Supabase)
- Daily 06:00 pipeline continues running

### What changes
- Every scraper output goes through validator before touching Supabase
- Every market data point has a source URL
- Every promo status is verified via search page
- Bad data goes to quarantine, not to dashboard
- Rules are code-reviewed and tested, not chat-fixed

---

## 6. Commitments

1. **No more local patches.** Every fix is a rule in `validator.py` that applies to all 71 communities, all 648 sub-community groups, all 1,586 listings.
2. **No more fabricated data.** If we don't have real sub-community comps, the listing shows "insufficient data" — never a community average pretending to be sub-community data.
3. **No more untracked scrapes.** Every API call is logged with URL, response, and run_id.
4. **No more "I think it's fixed."** Every rule has a test. Every test runs before deploy.
5. **You stop being the QA team.** The integrity dashboard tells us what's broken before you find it in the customer dashboard.
