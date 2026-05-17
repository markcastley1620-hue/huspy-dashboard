"""
Sync Huspy tracker data to Supabase in the dashboard-compatible format.
Matches the schema used by the Lovable dashboard frontend.
"""

import os
import json
import math
import requests
from collections import defaultdict
from datetime import datetime

SUPABASE_URL = "https://qwmjjrcdkrtoitwdsfhe.supabase.co"
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF3bWpqcmNka3J0b2l0d2RzZmhlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg2NTk3MjAsImV4cCI6MjA5NDIzNTcyMH0.FFnbLvx-JPZAYBwUv8remvNrwlH-AV0j5MovWw5UUkU"


def get_price_band(price: int, purpose: str) -> str:
    """Assign price to a band."""
    if purpose == "rent":
        if price < 50000:
            return "<50K"
        elif price < 75000:
            return "50-75K"
        elif price < 100000:
            return "75-100K"
        elif price < 150000:
            return "100-150K"
        elif price < 250000:
            return "150-250K"
        elif price < 500000:
            return "250-500K"
        else:
            return "500K+"
    else:  # sale
        if price < 1000000:
            return "<1M"
        elif price < 2000000:
            return "1-2M"
        elif price < 3500000:
            return "2-3.5M"
        elif price < 7000000:
            return "3.5-7M"
        elif price < 15000000:
            return "7-15M"
        else:
            return "15M+"


def compute_opportunities(snapshot: dict, market_data: dict = None) -> dict:
    """Compute deal scores using MARKET medians as the benchmark, not Huspy internals.

    Priority for market comparison:
    1. Market by_bed_type (community + bed + type) — tightest comp
    2. Market by_bed (community + bed) — good comp
    3. Market community-level avg — fallback
    """
    from statistics import median as stat_median
    listings = snapshot.get("listings", [])
    mkt = market_data or {}

    def get_market_benchmark(community, purpose, beds, ptype):
        """Get market median/avg for a listing from market scraper data."""
        comm_data = mkt.get(purpose, {}).get(community, {})
        if not comm_data:
            return None, None, None, None

        bed_key = str(beds) if beds > 0 else 'Studio'
        bt_key = f"{bed_key}|{ptype}" if ptype else None

        # Try bed+type first (tightest comp, most reliable)
        if bt_key and bt_key in comm_data.get('by_bed_type', {}):
            bt = comm_data['by_bed_type'][bt_key]
            if bt.get('count', 0) >= 2:
                return bt.get('median_price'), bt.get('avg_price'), bt.get('count', 0), f"{community} · {ptype} · {bed_key} BR (market)"

        # Try bed only — but only if the listing has no type, or the bed group
        # isn't dominated by a different property type
        if bed_key in comm_data.get('by_bed', {}):
            bd = comm_data['by_bed'][bed_key]
            if bd.get('count', 0) >= 3:
                # Check if there's a type-specific group that covers most of the bed group
                # If so, using the untyped group would be misleading for our listing's type
                if ptype:
                    # If a bed+type entry exists for a DIFFERENT type with most of the count,
                    # the bed-only median is biased toward that other type — skip
                    other_typed_counts = sum(
                        v.get('count', 0)
                        for k, v in comm_data.get('by_bed_type', {}).items()
                        if k.startswith(f"{bed_key}|") and k != bt_key
                    )
                    if other_typed_counts >= bd['count'] * 0.6:
                        return None, None, None, None
                return bd.get('median_price'), bd.get('avg_price'), bd.get('count', 0), f"{community} · {bed_key} BR (market)"

        return None, None, None, None

    def score_listing(l, market_median, market_avg, market_count, peer_level):
        """Score 0-100 based on market comparison. Higher = better deal."""
        price = l['price_num']
        gap_pct = round((price - market_median) / market_median * 100, 1) if market_median else 0
        dom = l.get('dom')

        score = 50
        # Price position vs market (biggest weight)
        if gap_pct < -20: score += 25
        elif gap_pct < -10: score += 18
        elif gap_pct < -5: score += 10
        elif gap_pct > 20: score -= 20
        elif gap_pct > 10: score -= 12
        elif gap_pct > 5: score -= 5
        # DOM freshness
        if dom is not None:
            if dom < 7: score += 10
            elif dom < 21: score += 5
            if dom > 30: score -= 8
            if dom > 60: score -= 12
        # Market data confidence
        if market_count and market_count >= 10: score += 5
        elif market_count and market_count >= 5: score += 2
        elif market_count and market_count < 3: score -= 10

        score = max(0, min(100, round(score)))

        # Verdict
        verdict = 'Monitor'
        if gap_pct < -10 and score >= 60: verdict = 'Signature'
        elif gap_pct < -5 and score >= 50: verdict = 'Hot'
        elif gap_pct > 15: verdict = 'Overpriced'
        elif gap_pct > 5 and (dom or 0) > 21: verdict = 'Price review'
        if dom and dom > 45 and gap_pct > 5: verdict = 'Price review'

        return {
            'listing_id': l.get('listing_id'),
            'url': l.get('url'),
            'agent': l.get('agent') or None,
            'community': l.get('community'),
            'sub_community': l.get('sub_community'),
            'beds': l.get('bedrooms'),
            'type': l.get('type'),
            'price': l['price_num'],
            'title': l.get('title', ''),
            'market_median': int(market_median) if market_median else None,
            'market_avg': int(market_avg) if market_avg else None,
            'market_count': market_count or 0,
            'peer_level': peer_level,
            'gap_pct': gap_pct,
            'dom': dom,
            'promo': l.get('promo'),
            'score': score,
            'action': verdict,
        }

    results = {'sale': [], 'rent': []}
    for l in listings:
        if not l.get('price_num') or l.get('bedrooms') is None:
            continue
        # Skip unattributed listings — no actionable agent
        if not l.get('agent'):
            continue
        # Skip listings that already have spend (Signature/Hot)
        if l.get('promo'):
            continue

        community = l.get('community')
        if not community:
            continue

        med, avg, count, peer_level = get_market_benchmark(
            community, l['purpose'], l['bedrooms'], l.get('type'))

        if med is None:
            continue

        scored = score_listing(l, med, avg, count, peer_level)
        results[l['purpose']].append(scored)

    # Sort and categorize
    opps = {}
    for purpose in ['sale', 'rent']:
        all_scored = results[purpose]
        underpriced = sorted([s for s in all_scored if s['gap_pct'] < -5 and s['score'] >= 45], key=lambda x: -x['score'])
        overpriced = sorted([s for s in all_scored if s['gap_pct'] > 10], key=lambda x: x['gap_pct'], reverse=True)
        stale = sorted([s for s in all_scored if (s['dom'] or 0) >= 30], key=lambda x: -(x['dom'] or 0))
        opps[purpose] = {
            'underpriced': underpriced,
            'overpriced': overpriced,
            'stale': stale,
        }

    # Coverage gaps
    coverage_gaps = []

    summary = {
        'sale': {'underpriced': len(opps['sale']['underpriced']), 'overpriced': len(opps['sale']['overpriced']), 'stale': len(opps['sale']['stale'])},
        'rent': {'underpriced': len(opps['rent']['underpriced']), 'overpriced': len(opps['rent']['overpriced']), 'stale': len(opps['rent']['stale'])},
        'coverage_gaps_count': 0,
    }

    return {'sale': opps['sale'], 'rent': opps['rent'], 'coverage_gaps': coverage_gaps, 'summary': summary}


def compute_peer_medians(snapshot: dict) -> dict:
    """Compute peer median prices per community + bed count for the snapshot."""
    from statistics import median as stat_median
    listings = snapshot.get("listings", [])
    peer_groups = defaultdict(list)
    for l in listings:
        if l.get('price_num') and l.get('community') and l.get('bedrooms') is not None:
            key = (l['community'], l['purpose'], l['bedrooms'])
            peer_groups[key].append(l['price_num'])

    medians = {}
    for (comm, purpose, beds), prices in peer_groups.items():
        if len(prices) < 2:
            continue
        med = int(stat_median(prices))
        medians.setdefault(purpose, {}).setdefault(comm, {})[str(beds) if beds > 0 else 'Studio'] = {
            'median': med,
            'count': len(prices),
            'min': min(prices),
            'max': max(prices),
        }
    return medians


def transform_snapshot(snapshot: dict, market_data: dict = None) -> dict:
    """Transform raw snapshot into the dashboard schema."""
    listings = snapshot.get("listings", [])
    date_str = snapshot.get("date", datetime.utcnow().strftime("%Y-%m-%d"))

    sale_listings = [l for l in listings if l["purpose"] == "sale"]
    rent_listings = [l for l in listings if l["purpose"] == "rent"]

    def build_community_data(filtered_listings, purpose):
        communities = defaultdict(list)
        for l in filtered_listings:
            c = l.get("community") or "Unknown"
            communities[c].append(l)

        total = len(filtered_listings)
        result = {}

        for comm, comm_listings in sorted(communities.items(), key=lambda x: -len(x[1])):
            count = len(comm_listings)

            # Beds breakdown with avg price per bed count
            beds = defaultdict(int)
            beds_prices = defaultdict(list)
            for l in comm_listings:
                b = l.get("bedrooms")
                if b is not None:
                    key = str(b) if b > 0 else "Studio"
                    beds[key] += 1
                    if l.get("price_num"):
                        beds_prices[key].append(l["price_num"])

            # Agents breakdown with avg price + per-bed prices
            agent_data = defaultdict(lambda: {"count": 0, "prices": [], "beds": defaultdict(lambda: {"count": 0, "prices": []})})
            for l in comm_listings:
                a = l.get("agent") or l.get("agent_name") or "Unattributed"
                agent_data[a]["count"] += 1
                if l.get("price_num"):
                    agent_data[a]["prices"].append(l["price_num"])
                    b = l.get("bedrooms")
                    if b is not None:
                        key = str(b) if b > 0 else "Studio"
                        agent_data[a]["beds"][key]["count"] += 1
                        agent_data[a]["beds"][key]["prices"].append(l["price_num"])

            agents = []
            for name, ad in sorted(agent_data.items(), key=lambda x: -x[1]["count"]):
                beds_out = {}
                for bk, bd in sorted(ad["beds"].items()):
                    beds_out[bk] = {
                        "count": bd["count"],
                        "avg_price": int(sum(bd["prices"]) / len(bd["prices"])) if bd["prices"] else None,
                    }
                agents.append({
                    "name": name,
                    "count": ad["count"],
                    "share_pct": round(ad["count"] / count * 100, 1) if count else 0,
                    "avg_price": int(sum(ad["prices"]) / len(ad["prices"])) if ad["prices"] else None,
                    "beds": beds_out,
                })

            # Average price
            prices = [l["price_num"] for l in comm_listings if l.get("price_num")]
            avg_price = int(sum(prices) / len(prices)) if prices else 0

            # Price bands
            bands = defaultdict(int)
            for l in comm_listings:
                if l.get("price_num"):
                    band = get_price_band(l["price_num"], purpose)
                    bands[band] += 1

            # Sub-communities
            sub_comms = defaultdict(list)
            for l in comm_listings:
                sc = l.get("sub_community")
                if sc:
                    sub_comms[sc].append(l)

            sub_community_data = {}
            for sc, sc_listings in sorted(sub_comms.items(), key=lambda x: -len(x[1])):
                sc_prices = [l["price_num"] for l in sc_listings if l.get("price_num")]
                # Bedroom breakdown per sub-community with avg price
                sc_beds = defaultdict(lambda: {"count": 0, "prices": []})
                for l in sc_listings:
                    b = l.get("bedrooms")
                    if b is not None:
                        key = str(b) if b > 0 else "Studio"
                        sc_beds[key]["count"] += 1
                        if l.get("price_num"):
                            sc_beds[key]["prices"].append(l["price_num"])
                beds_out = {}
                for bk in sorted(sc_beds.keys()):
                    bd = sc_beds[bk]
                    beds_out[bk] = {
                        "count": bd["count"],
                        "avg_price": int(sum(bd["prices"]) / len(bd["prices"])) if bd["prices"] else None,
                    }
                sub_community_data[sc] = {
                    "count": len(sc_listings),
                    "avg_price": int(sum(sc_prices) / len(sc_prices)) if sc_prices else 0,
                    "share_pct": None,
                    "market_total": None,
                    "beds": beds_out,
                }

            # Property type breakdown
            type_counts = defaultdict(lambda: {"sale": 0, "rent": 0, "total": 0})
            for l in comm_listings:
                t = l.get("type") or "Unknown"
                type_counts[t][l["purpose"]] += 1
                type_counts[t]["total"] += 1
            by_type = dict(sorted(type_counts.items(), key=lambda x: -x[1]["total"]))

            # Beds with avg price
            beds_with_price = {}
            for bk in sorted(beds.keys()):
                bp = beds_prices.get(bk, [])
                beds_with_price[bk] = {
                    "count": beds[bk],
                    "avg_price": int(sum(bp) / len(bp)) if bp else None,
                }

            result[comm] = {
                "count": count,
                "beds": beds_with_price,
                "agents": agents[:10],  # Top 10 agents per community
                "avg_price": avg_price,
                "share_pct": round(count / total * 100, 2) if total else 0,
                "price_bands": dict(bands),
                "market_total": None,  # Enriched later from market scrape
                "by_type": by_type,
                "sub_communities": sub_community_data,
            }

        return result

    # Compute opportunities (market-based) and Huspy peer medians
    opportunities = compute_opportunities(snapshot, market_data=market_data)
    peer_medians = compute_peer_medians(snapshot)

    # Compact listing-level data for agent drill-down
    # Format: [agent, community, sub_community, type, beds, price, dom, promo, psqft, sqft, purpose, title, url]
    listing_rows = []
    for l in listings:
        if not l.get('agent'):
            continue
        listing_rows.append([
            l.get('agent', ''),
            l.get('community', ''),
            l.get('sub_community', ''),
            l.get('type', ''),
            l.get('bedrooms'),
            l.get('price_num', 0),
            l.get('dom'),
            l.get('promo') or '',
            l.get('price_sqft'),
            l.get('size_sqft'),
            l.get('purpose', ''),
            l.get('title', ''),
            l.get('url', ''),
        ])

    return {
        "date": date_str,
        "sale": {
            "total": len(sale_listings),
            "by_community": build_community_data(sale_listings, "sale"),
        },
        "rent": {
            "total": len(rent_listings),
            "by_community": build_community_data(rent_listings, "rent"),
        },
        "opportunities": opportunities,
        "peer_medians": peer_medians,
        "listings": listing_rows,
        "listings_schema": ["agent","community","sub_community","type","beds","price","dom","promo","psqft","sqft","purpose","title","url"],
    }


def upsert_to_supabase(date_str: str, data: dict) -> bool:
    """Upsert transformed data to Supabase."""
    headers = {
        "apikey": ANON_KEY,
        "Authorization": f"Bearer {ANON_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "snapshot_date": date_str,
        "generated_at": datetime.utcnow().isoformat(),
        "data": data,
    }

    # Try update first (for existing rows)
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/market_intel_snapshots?snapshot_date=eq.{date_str}",
        headers={**headers, "Prefer": "return=representation"},
        json={"generated_at": payload["generated_at"], "data": data},
        timeout=15,
    )

    if resp.status_code == 200 and resp.json():
        return True

    # If no row to update, insert
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/market_intel_snapshots",
        headers={**headers, "Prefer": "return=minimal"},
        json=payload,
        timeout=15,
    )

    return resp.status_code in (200, 201)


def sync_snapshot(snapshot_path: str, market_path: str = None) -> bool:
    """Load a snapshot file, transform, and push to Supabase."""
    with open(snapshot_path) as f:
        snapshot = json.load(f)

    # Try to find market data
    market_data = None
    if market_path:
        with open(market_path) as f:
            market_data = json.load(f)
    else:
        # Auto-find latest market file
        data_dir = os.path.dirname(snapshot_path)
        market_files = sorted([f for f in os.listdir(data_dir) if f.startswith('market_') and f.endswith('.json')], reverse=True)
        if market_files:
            with open(os.path.join(data_dir, market_files[0])) as f:
                market_data = json.load(f)
            print(f"  Using market data: {market_files[0]}")

    date_str = snapshot.get("date")
    data = transform_snapshot(snapshot, market_data=market_data)

    print(f"  Syncing {date_str}: {data['sale']['total']} sale, {data['rent']['total']} rent, "
          f"{len(data['sale']['by_community'])} sale communities, {len(data['rent']['by_community'])} rent communities")

    success = upsert_to_supabase(date_str, data)
    print(f"  {'✓' if success else '✗'} Supabase upsert {'succeeded' if success else 'failed'}")
    return success


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        sync_snapshot(sys.argv[1])
    else:
        # Sync latest
        data_dir = "data"
        files = sorted([f for f in os.listdir(data_dir) if f.endswith(".json")])
        if files:
            sync_snapshot(os.path.join(data_dir, files[-1]))
        else:
            print("No snapshot files found")
