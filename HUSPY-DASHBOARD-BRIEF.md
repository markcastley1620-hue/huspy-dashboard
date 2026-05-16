# Huspy Dashboard — Standing Orders (v2)

## Audience
Huspy team — broker managers, team leads, exec. Internal tool.

## Cadence
- Ship something every day, 7 days a week
- Send brief at 06:00 Dubai time (02:00 UTC)
- First brief: 2026-05-17

## Priority 1 — Grade-A Redesign
- Benchmark: Linear, Stripe Sigma, Mercury
- Light theme (Apple/HubSpot style) — DONE
- Kill "Generated" KPI → "Communities gaining share" — DONE
- KPI typography: number dominates, label small/uppercase/muted, delta+arrow below — DONE
- Movers: inline mini sparkbars — DONE
- Communities table: sortable, sticky header, subtle dividers, hover — DONE
- Sticky filter bar: search (/ keybind), min market slider, Huspy-only toggle — DONE
- Colors: #10b981 / #ef4444 — DONE
- Typography: Inter, tabular figures — DONE
- Mobile: stacked cards under 768px — DONE
- Sale/Rent persist via localStorage — DONE
- Small-n flag — DONE

## Priority 2 — Value Extraction
- Pricing position panel: Huspy median psqft vs market median psqft per community
- Coverage gaps: high market count, Huspy share 0/near-zero, sorted by market size
- Concentration view: % of Huspy in top 5/10/20 communities
- Agents page: listings per agent, top communities, pricing position, sortable
- Communities drill-down: listings, price distribution, share-over-time if history
- Remove anything that doesn't drive a decision

## Priority 3 — Opportunity Engine (THE commercial value page)
Management opens this every morning. Surfaces listings that should earn viewings/leads but aren't.

### Underpriced Opportunities
Definition:
- Compare each Huspy listing to sub-location peer set (same tower/cluster/sub-community, same beds, same property type)
- Sub-location level, NOT community level
- Priced below peer median (configurable threshold, default −5%)
- Peer set n ≥ 5 (flag n < 5 as "thin peer set" but still show)
- Currently NOT on Signature or Hot
- Weight by DOM: fresh underpriced = strongest signal. Stale (DOM > 60) = "investigate" flag

View columns:
- Agent
- Property (sub-location + beds/BUA)
- Asking price + psqft
- Peer median + gap %
- Peer set size (n)
- Days on market
- Current promotional status
- Recommended action: Signature / Hot / investigate
- "Deal score" — composite of gap %, peer-set confidence, DOM signal
- Sortable by deal score desc default
- Exportable to CSV

### Overpriced (second tab)
Same logic inverted. High DOM + above peer median = price-reduction conversation needed.

## Data Scope — EXPANDED
Original read-only restriction is LIFTED. Can extend the sweep to pull:
- Sub-location / tower / cluster
- Days on market
- Listing description
- BUA (built-up area)
- Beds/baths
- Promotional status (Signature / Hot)
- Any other field needed for opportunity engine
FLAG every scope change in morning brief.

## Brief Format (under 200 words)
```
HUSPY STOCK · {DATE}

SHIPPED
• {one-line description}
• Why it matters: {one sentence}
• Commit: {URL}

DATA HEALTH
• Listings snapshot: {count} (Δ {±n} vs yesterday)
• Scope changes: {new fields now collected, or "none"}
• Anomalies: {none / list}

OPPORTUNITIES TODAY
• Underpriced (recommend spend): {count}
• Overpriced (recommend price talk): {count}
• Top 1 deal: {agent} — {property} — {gap%} below peer median

NEXT 3 CANDIDATES (ranked)
1. {idea} — {why}
2. {idea} — {why}
3. {idea} — {why}

BLOCKERS
{none, or one line}
```

## Rules
- Don't break existing routes or data contracts without flagging
- Data scope expansion allowed — flag in brief
- Data quality issues → flag, don't paper over
- Never name source portal in UI copy. Use "current market listings" / "live market"
- "Signature" and "Hot" are fine — internal spend tier terms
- Tabular figures everywhere. Inter or Geist only.

## Dashboard
- Live: https://markcastley1620-hue.github.io/huspy-dashboard/
- Repo: markcastley1620-hue/huspy-dashboard (gh-pages branch)
- GitHub token: ghp_A9...5Y3E (nexus, fine-grained, 90 days)
- Deploy: git push → auto-deploy ~30s
