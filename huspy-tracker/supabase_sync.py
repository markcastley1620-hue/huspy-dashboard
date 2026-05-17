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


def compute_opportunities(snapshot: dict) -> dict:
    """Compute peer medians, deal scores, and opportunity lists per listing."""
    from statistics import median as stat_median
    listings = snapshot.get("listings", [])

    # Build peer groups: community + purpose + bedrooms
    peer_groups = defaultdict(list)
    for l in listings:
        if l.get('price_num') and l.get('community') and l.get('bedrooms') is not None:
            key = (l['community'], l['purpose'], l['bedrooms'])
            peer_groups[key].append(l)

    # Also build sub-community peer groups for tighter comps
    sub_peer_groups = defaultdict(list)
    for l in listings:
        if l.get('price_num') and l.get('sub_community') and l.get('bedrooms') is not None:
            key = (l['sub_community'], l['community'], l['purpose'], l['bedrooms'])
            sub_peer_groups[key].append(l)

    def score_listing(l, peers, peer_level):
        """Score 0-100 for deal quality. Higher = better candidate for spend."""
        prices = sorted([p['price_num'] for p in peers])
        med = stat_median(prices)
        avg = sum(prices) / len(prices)
        price = l['price_num']
        gap_pct = round((price - med) / med * 100, 1) if med else 0
        rank = sum(1 for p in prices if p < price) + 1
        rank_pctile = round((1 - (rank - 1) / len(prices)) * 100) if len(prices) else 50
        promoted = sum(1 for p in peers if p.get('promo'))

        score = 50
        # Price position (biggest weight)
        if rank == 1 and len(prices) >= 3: score += 25
        elif rank_pctile >= 80: score += 20
        elif rank_pctile >= 60: score += 10
        elif rank_pctile <= 30: score -= 15
        # Gap from median
        if gap_pct < 0: score += min(abs(gap_pct) * 0.8, 15)
        if gap_pct > 10: score -= min(gap_pct * 0.8, 20)
        # DOM
        dom = l.get('dom')
        if dom is not None:
            if dom < 7: score += 12
            elif dom < 21: score += 6
            if dom > 30: score -= 10
            if dom > 60: score -= 15
        # Peer set quality
        if len(prices) >= 10: score += 3
        if len(prices) < 3: score -= 8
        # Competition
        if promoted == 0 and len(prices) >= 3: score += 5

        score = max(0, min(100, round(score)))

        # Verdict
        verdict = 'Monitor'
        if score >= 65: verdict = 'Signature'
        elif score >= 50: verdict = 'Hot'
        elif gap_pct > 10 and (dom or 0) > 14: verdict = 'Price first'
        if dom and dom > 45 and gap_pct > 5: verdict = 'Price first'
        if gap_pct > 20: verdict = 'Price first'

        return {
            'listing_id': l.get('listing_id'),
            'url': l.get('url'),
            'agent': l.get('agent') or 'Unknown',
            'community': l.get('community'),
            'sub_community': l.get('sub_community'),
            'beds': l.get('bedrooms'),
            'type': l.get('type'),
            'price': l['price_num'],
            'title': l.get('title', ''),
            'peer_median': int(med),
            'market_avg': int(avg),
            'market_count': len(prices),
            'peer_level': peer_level,
            'gap_pct': gap_pct,
            'rank': rank,
            'dom': dom,
            'promo': l.get('promo'),
            'promoted_peers': promoted,
            'score': score,
            'action': verdict,
        }

    results = {'sale': [], 'rent': []}
    for l in listings:
        if not l.get('price_num') or l.get('bedrooms') is None:
            continue
        # Try sub-community peers first (tighter comp)
        sub_key = (l.get('sub_community'), l.get('community'), l['purpose'], l['bedrooms'])
        comm_key = (l.get('community'), l['purpose'], l['bedrooms'])
        if l.get('sub_community') and sub_key in sub_peer_groups and len(sub_peer_groups[sub_key]) >= 3:
            peers = sub_peer_groups[sub_key]
            peer_level = f"{l['sub_community']} · {l['bedrooms'] if l['bedrooms'] else 'Studio'} BR"
        elif comm_key in peer_groups and len(peer_groups[comm_key]) >= 2:
            peers = peer_groups[comm_key]
            peer_level = f"{l['community']} · {l['bedrooms'] if l['bedrooms'] else 'Studio'} BR"
        else:
            continue
        scored = score_listing(l, peers, peer_level)
        results[l['purpose']].append(scored)

    # Sort and categorize
    opps = {}
    for purpose in ['sale', 'rent']:
        all_scored = results[purpose]
        underpriced = sorted([s for s in all_scored if s['gap_pct'] < -5 and s['score'] >= 50], key=lambda x: -x['score'])
        overpriced = sorted([s for s in all_scored if s['gap_pct'] > 10], key=lambda x: x['gap_pct'], reverse=True)
        stale = sorted([s for s in all_scored if (s['dom'] or 0) >= 30], key=lambda x: -(x['dom'] or 0))
        opps[purpose] = {
            'underpriced': underpriced[:50],
            'overpriced': overpriced[:50],
            'stale': stale[:50],
        }

    # Coverage gaps: large market communities where Huspy has low share
    # (this will be filled after market enrichment if available)
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


def transform_snapshot(snapshot: dict) -> dict:
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

    # Compute opportunities and peer medians
    opportunities = compute_opportunities(snapshot)
    peer_medians = compute_peer_medians(snapshot)

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


def sync_snapshot(snapshot_path: str) -> bool:
    """Load a snapshot file, transform, and push to Supabase."""
    with open(snapshot_path) as f:
        snapshot = json.load(f)

    date_str = snapshot.get("date")
    data = transform_snapshot(snapshot)

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
