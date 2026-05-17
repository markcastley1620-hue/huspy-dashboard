"""
Data integrity validator for Huspy Market Intel.
All data quality rules live here. No bypasses. No patches.
Every rule applies uniformly to the entire dataset.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime


@dataclass
class ValidationResult:
    passed: bool
    rule_id: str
    rule_name: str
    reason: str = ""
    record_id: str = ""
    field: str = ""
    value: Any = None


@dataclass
class RejectedRecord:
    listing_id: str
    scrape_run_id: str
    reasons: list
    raw_data: dict
    rejected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ============================================================
# RULE DEFINITIONS
# ============================================================

ALLOWED_TYPES = {
    "Apartment", "Villa", "Townhouse", "Office", "Penthouse",
    "Shop", "Residential Floor", "Residential Plot", "Commercial Floor",
}

ALLOWED_PURPOSES = {"sale", "rent"}
ALLOWED_PROMOS = {"Signature", "Hot", None}
ALLOWED_FREQUENCIES = {"yearly", "monthly", "weekly", "daily", None}


def r01_bedrooms_required(record: dict) -> ValidationResult:
    """R01: bedrooms must not be NULL"""
    v = record.get("bedrooms")
    return ValidationResult(
        passed=v is not None,
        rule_id="R01", rule_name="bedrooms_required",
        reason="" if v is not None else "bedrooms is NULL",
        record_id=record.get("listing_id", ""),
        field="bedrooms", value=v,
    )


def r02_price_positive(record: dict) -> ValidationResult:
    """R02: price_num must be > 0"""
    v = record.get("price_num")
    return ValidationResult(
        passed=v is not None and v > 0,
        rule_id="R02", rule_name="price_positive",
        reason="" if (v and v > 0) else f"price_num={v}",
        record_id=record.get("listing_id", ""),
        field="price_num", value=v,
    )


def r03_type_valid(record: dict) -> ValidationResult:
    """R03: type must be in allowed ENUM"""
    v = record.get("type")
    return ValidationResult(
        passed=v in ALLOWED_TYPES,
        rule_id="R03", rule_name="type_valid",
        reason="" if v in ALLOWED_TYPES else f"type={v} not in {ALLOWED_TYPES}",
        record_id=record.get("listing_id", ""),
        field="type", value=v,
    )


def r04_purpose_valid(record: dict) -> ValidationResult:
    """R04: purpose must be sale or rent"""
    v = record.get("purpose")
    return ValidationResult(
        passed=v in ALLOWED_PURPOSES,
        rule_id="R04", rule_name="purpose_valid",
        reason="" if v in ALLOWED_PURPOSES else f"purpose={v}",
        record_id=record.get("listing_id", ""),
        field="purpose", value=v,
    )


def r05_listing_id_present(record: dict) -> ValidationResult:
    """R05: listing_id must be present and non-empty"""
    v = record.get("listing_id")
    return ValidationResult(
        passed=v is not None and v != "",
        rule_id="R05", rule_name="listing_id_present",
        reason="" if (v and v != "") else "listing_id missing",
        record_id=record.get("listing_id", ""),
        field="listing_id", value=v,
    )


def r06_sale_price_range(record: dict) -> ValidationResult:
    """R06: Sale price between 100K and 200M AED"""
    if record.get("purpose") != "sale":
        return ValidationResult(passed=True, rule_id="R06", rule_name="sale_price_range")
    v = record.get("price_num", 0)
    ok = 100_000 <= v <= 200_000_000
    return ValidationResult(
        passed=ok, rule_id="R06", rule_name="sale_price_range",
        reason="" if ok else f"sale price {v} out of range [100K-200M]",
        record_id=record.get("listing_id", ""),
        field="price_num", value=v,
    )


def r07_rent_price_range(record: dict) -> ValidationResult:
    """R07: Rent price between 5K and 50M AED/yr"""
    if record.get("purpose") != "rent":
        return ValidationResult(passed=True, rule_id="R07", rule_name="rent_price_range")
    v = record.get("price_num", 0)
    ok = 5_000 <= v <= 50_000_000
    return ValidationResult(
        passed=ok, rule_id="R07", rule_name="rent_price_range",
        reason="" if ok else f"rent price {v} out of range [5K-50M]",
        record_id=record.get("listing_id", ""),
        field="price_num", value=v,
    )


def r08_size_range(record: dict) -> ValidationResult:
    """R08: size_sqft between 100 and 100,000 when present"""
    v = record.get("size_sqft")
    if v is None or v == 0:
        return ValidationResult(passed=True, rule_id="R08", rule_name="size_range")
    ok = 100 <= v <= 100_000
    return ValidationResult(
        passed=ok, rule_id="R08", rule_name="size_range",
        reason="" if ok else f"size_sqft={v} out of range [100-100K]",
        record_id=record.get("listing_id", ""),
        field="size_sqft", value=v,
    )


def r09_dom_range(record: dict) -> ValidationResult:
    """R09: dom between 0 and 730 when present"""
    v = record.get("dom")
    if v is None:
        return ValidationResult(passed=True, rule_id="R09", rule_name="dom_range")
    ok = 0 <= v <= 730
    return ValidationResult(
        passed=ok, rule_id="R09", rule_name="dom_range",
        reason="" if ok else f"dom={v} out of range [0-730]",
        record_id=record.get("listing_id", ""),
        field="dom", value=v,
    )


def r10_bedrooms_range(record: dict) -> ValidationResult:
    """R10: bedrooms between 0 and 10 when present"""
    v = record.get("bedrooms")
    if v is None:
        return ValidationResult(passed=True, rule_id="R10", rule_name="bedrooms_range")
    ok = 0 <= v <= 10
    return ValidationResult(
        passed=ok, rule_id="R10", rule_name="bedrooms_range",
        reason="" if ok else f"bedrooms={v} out of range [0-10]",
        record_id=record.get("listing_id", ""),
        field="bedrooms", value=v,
    )


def r11_psqft_consistency(record: dict) -> ValidationResult:
    """R11: price_sqft must equal price_num / size_sqft (±5%)"""
    price = record.get("price_num")
    size = record.get("size_sqft")
    psqft = record.get("price_sqft")
    if not price or not size or size == 0 or not psqft:
        return ValidationResult(passed=True, rule_id="R11", rule_name="psqft_consistency")
    expected = price / size
    diff_pct = abs(expected - psqft) / expected * 100 if expected else 0
    ok = diff_pct <= 5
    return ValidationResult(
        passed=ok, rule_id="R11", rule_name="psqft_consistency",
        reason="" if ok else f"psqft={psqft} vs expected={expected:.0f} ({diff_pct:.1f}% diff)",
        record_id=record.get("listing_id", ""),
        field="price_sqft", value=psqft,
    )


def r12_rent_frequency(record: dict) -> ValidationResult:
    """R12: frequency should be set for rent listings"""
    if record.get("purpose") != "rent":
        return ValidationResult(passed=True, rule_id="R12", rule_name="rent_frequency")
    v = record.get("frequency")
    return ValidationResult(
        passed=v is not None,
        rule_id="R12", rule_name="rent_frequency",
        reason="" if v else "rent listing missing frequency",
        record_id=record.get("listing_id", ""),
        field="frequency", value=v,
    )


def r13_community_registered(record: dict, community_registry: set = None) -> ValidationResult:
    """R13: community must exist in community_registry"""
    if community_registry is None:
        return ValidationResult(passed=True, rule_id="R13", rule_name="community_registered")
    v = record.get("community")
    ok = v in community_registry
    return ValidationResult(
        passed=ok, rule_id="R13", rule_name="community_registered",
        reason="" if ok else f"community={v} not in registry",
        record_id=record.get("listing_id", ""),
        field="community", value=v,
    )


def r14_sub_community_present(record: dict) -> ValidationResult:
    """R14: sub_community should not be NULL"""
    v = record.get("sub_community")
    return ValidationResult(
        passed=v is not None and v != "",
        rule_id="R14", rule_name="sub_community_present",
        reason="" if (v and v != "") else "sub_community missing",
        record_id=record.get("listing_id", ""),
        field="sub_community", value=v,
    )


def r15_url_format(record: dict) -> ValidationResult:
    """R15: url must match Bayut property URL pattern"""
    v = record.get("url", "")
    ok = bool(re.match(r"^/property/details-\d+\.html$", v or ""))
    return ValidationResult(
        passed=ok, rule_id="R15", rule_name="url_format",
        reason="" if ok else f"url={v} doesn't match pattern",
        record_id=record.get("listing_id", ""),
        field="url", value=v,
    )


# ============================================================
# MARKET COMP RULES
# ============================================================

def rm01_comp_count_minimum(comp: dict) -> ValidationResult:
    """RM01: comp_count must be >= 1"""
    v = comp.get("count", 0)
    return ValidationResult(
        passed=v >= 1, rule_id="RM01", rule_name="comp_count_minimum",
        reason="" if v >= 1 else f"comp_count={v}",
        field="count", value=v,
    )


def rm02_comp_median_positive(comp: dict) -> ValidationResult:
    """RM02: median_price must be > 0"""
    v = comp.get("median_price", 0)
    return ValidationResult(
        passed=v > 0, rule_id="RM02", rule_name="comp_median_positive",
        reason="" if v > 0 else f"median_price={v}",
        field="median_price", value=v,
    )


def rm03_comp_has_source(comp: dict) -> ValidationResult:
    """RM03: comp must have a known source"""
    v = comp.get("source")
    ok = v is not None and v != "unknown"
    return ValidationResult(
        passed=ok, rule_id="RM03", rule_name="comp_has_source",
        reason="" if ok else f"source={v}",
        field="source", value=v,
    )


def rm04_comp_no_community_injection(comp: dict) -> ValidationResult:
    """RM04: comp must not be community_fallback or community_upgrade"""
    v = comp.get("source", "")
    bad = v in ("community_fallback", "community_upgrade")
    return ValidationResult(
        passed=not bad, rule_id="RM04", rule_name="comp_no_community_injection",
        reason="" if not bad else f"source={v} is injected data",
        field="source", value=v,
    )


# ============================================================
# VALIDATION ENGINE
# ============================================================

# All listing rules in order
LISTING_RULES = [
    r01_bedrooms_required,
    r02_price_positive,
    r03_type_valid,
    r04_purpose_valid,
    r05_listing_id_present,
    r06_sale_price_range,
    r07_rent_price_range,
    r08_size_range,
    r09_dom_range,
    r10_bedrooms_range,
    r11_psqft_consistency,
    r12_rent_frequency,
    r14_sub_community_present,
    r15_url_format,
]

# Critical rules — records failing these go to quarantine
CRITICAL_RULES = {"R01", "R02", "R03", "R04", "R05", "R06", "R07"}

# Warning rules — records pass but are flagged
WARNING_RULES = {"R08", "R09", "R10", "R11", "R12", "R13", "R14", "R15"}

COMP_RULES = [rm01_comp_count_minimum, rm02_comp_median_positive, rm03_comp_has_source, rm04_comp_no_community_injection]


def validate_listing(record: dict, community_registry: set = None) -> tuple[bool, list[ValidationResult]]:
    """Validate a single listing record against all rules.
    Returns (accepted, results) where accepted=False means quarantine."""
    results = []
    for rule_fn in LISTING_RULES:
        results.append(rule_fn(record))
    if community_registry:
        results.append(r13_community_registered(record, community_registry))

    # Record is rejected if ANY critical rule fails
    critical_failures = [r for r in results if not r.passed and r.rule_id in CRITICAL_RULES]
    accepted = len(critical_failures) == 0
    return accepted, results


def validate_snapshot(listings: list, community_registry: set = None) -> dict:
    """Validate an entire snapshot. Returns audit report."""
    accepted = []
    rejected = []
    rule_stats = {}

    seen_ids = set()
    for record in listings:
        # Duplicate check (R05 extension)
        lid = record.get("listing_id")
        if lid in seen_ids:
            rejected.append(RejectedRecord(
                listing_id=lid, scrape_run_id="", reasons=["duplicate_listing_id"],
                raw_data=record,
            ))
            continue
        if lid:
            seen_ids.add(lid)

        ok, results = validate_listing(record, community_registry)
        for r in results:
            if r.rule_id not in rule_stats:
                rule_stats[r.rule_id] = {"name": r.rule_name, "passed": 0, "failed": 0, "total": 0}
            rule_stats[r.rule_id]["total"] += 1
            if r.passed:
                rule_stats[r.rule_id]["passed"] += 1
            else:
                rule_stats[r.rule_id]["failed"] += 1

        if ok:
            accepted.append(record)
        else:
            reasons = [r.reason for r in results if not r.passed and r.rule_id in CRITICAL_RULES]
            rejected.append(RejectedRecord(
                listing_id=lid or "unknown", scrape_run_id="",
                reasons=reasons, raw_data=record,
            ))

    return {
        "total": len(listings),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "accepted_records": accepted,
        "rejected_records": rejected,
        "rule_stats": rule_stats,
    }


def validate_market_comp(comp: dict) -> tuple[bool, list[ValidationResult]]:
    """Validate a single market comp entry."""
    results = [rule_fn(comp) for rule_fn in COMP_RULES]
    ok = all(r.passed for r in results)
    return ok, results


# ============================================================
# REPORTING
# ============================================================

def print_report(audit: dict):
    """Print human-readable validation report."""
    print(f"\n{'='*60}")
    print(f"DATA INTEGRITY REPORT")
    print(f"{'='*60}")
    print(f"Total records:  {audit['total']}")
    print(f"Accepted:       {audit['accepted']} ({audit['accepted']/audit['total']*100:.1f}%)")
    print(f"Rejected:       {audit['rejected']} ({audit['rejected']/audit['total']*100:.1f}%)")
    print(f"\nRule Results:")
    print(f"{'Rule':<8} {'Name':<25} {'Pass':>6} {'Fail':>6} {'Rate':>8}")
    print(f"{'-'*55}")
    for rule_id in sorted(audit["rule_stats"].keys()):
        s = audit["rule_stats"][rule_id]
        rate = s["passed"] / s["total"] * 100 if s["total"] else 0
        flag = "❌" if s["failed"] > 0 and rule_id in CRITICAL_RULES else "⚠" if s["failed"] > 0 else "✅"
        print(f"{flag} {rule_id:<6} {s['name']:<25} {s['passed']:>6} {s['failed']:>6} {rate:>7.1f}%")

    if audit["rejected_records"]:
        print(f"\nRejected Records (first 10):")
        for r in audit["rejected_records"][:10]:
            print(f"  {r.listing_id}: {', '.join(r.reasons)}")


if __name__ == "__main__":
    import json
    with open("data/2026-05-17.json") as f:
        snap = json.load(f)
    from market_scraper import COMMUNITY_SLUGS
    registry = set(COMMUNITY_SLUGS.keys())
    audit = validate_snapshot(snap["listings"], community_registry=registry)
    print_report(audit)
