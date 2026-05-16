"""
Analytics engine for Huspy listing data.
Produces market intelligence from daily snapshots.
"""

import json
import os
from collections import defaultdict
from datetime import datetime


def load_snapshot(date_str: str = None, data_dir: str = "data") -> dict | None:
    """Load a daily snapshot. If no date, load the latest."""
    if date_str:
        path = os.path.join(data_dir, f"{date_str}.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return None

    # Find latest file
    files = sorted([f for f in os.listdir(data_dir) if f.endswith(".json")], reverse=True)
    if files:
        with open(os.path.join(data_dir, files[0])) as f:
            return json.load(f)
    return None


def load_previous_snapshot(current_date: str, data_dir: str = "data") -> dict | None:
    """Load the snapshot before the given date."""
    files = sorted([f for f in os.listdir(data_dir) if f.endswith(".json")], reverse=True)
    for f in files:
        if f.replace(".json", "") < current_date:
            with open(os.path.join(data_dir, f)) as fh:
                return json.load(fh)
    return None


def analyze(snapshot: dict) -> dict:
    """Produce full analytics from a snapshot."""
    listings = snapshot.get("listings", [])

    # Overall counts
    total = len(listings)
    sale = [l for l in listings if l["purpose"] == "sale"]
    rent = [l for l in listings if l["purpose"] == "rent"]

    # By type
    by_type = defaultdict(lambda: {"sale": 0, "rent": 0, "total": 0})
    for l in listings:
        t = l.get("type") or "Unknown"
        by_type[t][l["purpose"]] += 1
        by_type[t]["total"] += 1

    # By community
    by_community = defaultdict(lambda: {
        "sale": 0, "rent": 0, "total": 0,
        "avg_sale_price": 0, "avg_rent_price": 0,
        "sale_prices": [], "rent_prices": [],
        "by_type": defaultdict(lambda: {"sale": 0, "rent": 0, "total": 0}),
    })
    for l in listings:
        c = l.get("community") or "Unknown"
        by_community[c][l["purpose"]] += 1
        by_community[c]["total"] += 1
        if l.get("price_num"):
            by_community[c][f"{l['purpose']}_prices"].append(l["price_num"])
        ptype = l.get("type") or "Unknown"
        by_community[c]["by_type"][ptype][l["purpose"]] += 1
        by_community[c]["by_type"][ptype]["total"] += 1

    # Calculate averages and convert nested defaultdicts
    for c, data in by_community.items():
        if data["sale_prices"]:
            data["avg_sale_price"] = int(sum(data["sale_prices"]) / len(data["sale_prices"]))
        if data["rent_prices"]:
            data["avg_rent_price"] = int(sum(data["rent_prices"]) / len(data["rent_prices"]))
        del data["sale_prices"]
        del data["rent_prices"]
        data["by_type"] = dict(sorted(data["by_type"].items(), key=lambda x: -x[1]["total"]))

    # By sub-community (top detail)
    by_sub = defaultdict(lambda: {"sale": 0, "rent": 0, "total": 0})
    for l in listings:
        sc = l.get("sub_community")
        if sc:
            by_sub[sc][l["purpose"]] += 1
            by_sub[sc]["total"] += 1

    # By tower (where applicable)
    by_tower = defaultdict(lambda: {"sale": 0, "rent": 0, "total": 0})
    for l in listings:
        t = l.get("tower")
        if t:
            by_tower[t][l["purpose"]] += 1
            by_tower[t]["total"] += 1

    # By agent
    by_agent = defaultdict(lambda: {"sale": 0, "rent": 0, "total": 0})
    for l in listings:
        a = l.get("agent") or "Unknown"
        by_agent[a][l["purpose"]] += 1
        by_agent[a]["total"] += 1

    # Price stats
    sale_prices = [l["price_num"] for l in sale if l.get("price_num")]
    rent_prices = [l["price_num"] for l in rent if l.get("price_num")]

    return {
        "date": snapshot.get("date"),
        "total": total,
        "sale_count": len(sale),
        "rent_count": len(rent),
        "avg_sale_price": int(sum(sale_prices) / len(sale_prices)) if sale_prices else 0,
        "avg_rent_price": int(sum(rent_prices) / len(rent_prices)) if rent_prices else 0,
        "median_sale_price": sorted(sale_prices)[len(sale_prices)//2] if sale_prices else 0,
        "median_rent_price": sorted(rent_prices)[len(rent_prices)//2] if rent_prices else 0,
        "by_type": dict(sorted(by_type.items(), key=lambda x: -x[1]["total"])),
        "by_community": dict(sorted(by_community.items(), key=lambda x: -x[1]["total"])),
        "by_sub_community": dict(sorted(by_sub.items(), key=lambda x: -x[1]["total"])),
        "by_tower": dict(sorted(by_tower.items(), key=lambda x: -x[1]["total"])),
        "by_agent": dict(sorted(by_agent.items(), key=lambda x: -x[1]["total"])),
        "off_plan_count": sum(1 for l in listings if l.get("off_plan")),
        "verified_count": sum(1 for l in listings if l.get("verified")),
    }


def compare(current: dict, previous: dict) -> dict:
    """Compare two analytics snapshots to find changes."""
    changes = {
        "total_change": current["total"] - previous["total"],
        "sale_change": current["sale_count"] - previous["sale_count"],
        "rent_change": current["rent_count"] - previous["rent_count"],
        "communities_gained": [],
        "communities_lost": [],
        "community_changes": {},
    }

    curr_comms = set(current["by_community"].keys())
    prev_comms = set(previous["by_community"].keys())

    changes["communities_gained"] = list(curr_comms - prev_comms)
    changes["communities_lost"] = list(prev_comms - curr_comms)

    for comm in curr_comms & prev_comms:
        curr_total = current["by_community"][comm]["total"]
        prev_total = previous["by_community"][comm]["total"]
        diff = curr_total - prev_total
        if diff != 0:
            changes["community_changes"][comm] = {
                "change": diff,
                "current": curr_total,
                "previous": prev_total,
            }

    # Sort by biggest change
    changes["community_changes"] = dict(
        sorted(changes["community_changes"].items(), key=lambda x: abs(x[1]["change"]), reverse=True)
    )

    return changes
