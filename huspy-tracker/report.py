"""
Telegram report formatter for Huspy market intelligence.
Generates a clean, easy-to-consume daily message.
"""

import json
import os
from analytics import analyze, load_snapshot, load_previous_snapshot, compare


def format_number(n: int) -> str:
    """Format number with commas."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}K" if n >= 10_000 else f"{n:,}"
    return str(n)


def change_indicator(n: int) -> str:
    if n > 0:
        return f"↑{n}"
    elif n < 0:
        return f"↓{abs(n)}"
    return "→0"


def load_market_data(date_str: str, data_dir: str = "data") -> dict | None:
    """Load market comparison data for a date."""
    path = os.path.join(data_dir, f"market_{date_str}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    # Fall back to latest market file
    files = sorted([f for f in os.listdir(data_dir) if f.startswith("market_") and f.endswith(".json")], reverse=True)
    if files:
        with open(os.path.join(data_dir, files[0])) as f:
            return json.load(f)
    return None


def generate_report(date: str = None) -> str:
    """Generate daily Telegram report."""
    snapshot = load_snapshot(date)
    if not snapshot:
        return "⚠️ No data available for report."

    stats = analyze(snapshot)
    date_str = stats["date"]
    market = load_market_data(date_str)

    # Try to load previous day for comparison
    prev_snapshot = load_previous_snapshot(date_str)
    changes = None
    if prev_snapshot:
        prev_stats = analyze(prev_snapshot)
        changes = compare(stats, prev_stats)

    lines = []

    # Header
    lines.append(f"⬡ HUSPY MARKET INTEL — {date_str}")
    lines.append("")

    # Overview
    total_ch = f" ({change_indicator(changes['total_change'])})" if changes else ""
    sale_ch = f" ({change_indicator(changes['sale_change'])})" if changes else ""
    rent_ch = f" ({change_indicator(changes['rent_change'])})" if changes else ""

    lines.append(f"📊 PORTFOLIO OVERVIEW")
    lines.append(f"Total: {stats['total']}{total_ch}")
    lines.append(f"Sale: {stats['sale_count']}{sale_ch} | Rent: {stats['rent_count']}{rent_ch}")
    lines.append(f"Off-Plan: {stats['off_plan_count']} | Verified: {stats['verified_count']}")
    lines.append("")

    # Pricing
    lines.append(f"💰 PRICING")
    lines.append(f"Avg Sale: AED {format_number(stats['avg_sale_price'])} | Median: AED {format_number(stats['median_sale_price'])}")
    lines.append(f"Avg Rent: AED {format_number(stats['avg_rent_price'])}/yr | Median: AED {format_number(stats['median_rent_price'])}/yr")
    lines.append("")

    # Property type split
    lines.append(f"🏠 BY TYPE")
    for ptype, data in list(stats["by_type"].items())[:6]:
        lines.append(f"  {ptype}: {data['total']} (S:{data['sale']} R:{data['rent']})")
    lines.append("")

    # Market share by type (rent vs sale)
    if market:
        lines.append(f"📊 MARKET SHARE")
        # Total rent market vs huspy rent
        total_market_rent = sum(c.get("total_market", 0) for c in market.get("rent", {}).values() if isinstance(c, dict))
        total_market_sale = sum(c.get("total_market", 0) for c in market.get("sale", {}).values() if isinstance(c, dict))
        rent_share = f"{stats['rent_count']/total_market_rent*100:.1f}%" if total_market_rent else "n/a"
        sale_share = f"{stats['sale_count']/total_market_sale*100:.1f}%" if total_market_sale else "n/a"
        lines.append(f"  Rent: {stats['rent_count']}/{format_number(total_market_rent)} = {rent_share}")
        lines.append(f"  Sale: {stats['sale_count']}/{format_number(total_market_sale)} = {sale_share}")
        lines.append("")

    # Top communities (top 15)
    lines.append(f"📍 TOP COMMUNITIES")
    top_comms = list(stats["by_community"].items())[:15]
    for comm, data in top_comms:
        parts = [f"{comm}: {data['total']}"]

        # Sale share
        sale_share_str = ""
        rent_share_str = ""
        if market:
            mkt_sale = market.get("sale", {}).get(comm, {})
            mkt_rent = market.get("rent", {}).get(comm, {})
            if data["sale"] and mkt_sale.get("total_market"):
                pct = data["sale"] / mkt_sale["total_market"] * 100
                sale_share_str = f"S:{data['sale']}/{format_number(mkt_sale['total_market'])}={pct:.1f}%"
            elif data["sale"]:
                sale_share_str = f"S:{data['sale']}"
            if data["rent"] and mkt_rent.get("total_market"):
                pct = data["rent"] / mkt_rent["total_market"] * 100
                rent_share_str = f"R:{data['rent']}/{format_number(mkt_rent['total_market'])}={pct:.1f}%"
            elif data["rent"]:
                rent_share_str = f"R:{data['rent']}"
        else:
            if data["sale"]: sale_share_str = f"S:{data['sale']}"
            if data["rent"]: rent_share_str = f"R:{data['rent']}"

        share_parts = [s for s in [sale_share_str, rent_share_str] if s]
        if share_parts:
            parts.append(" | ".join(share_parts))

        change_str = ""
        if changes and comm in changes.get("community_changes", {}):
            ch = changes["community_changes"][comm]["change"]
            change_str = f" {change_indicator(ch)}"

        lines.append(f"  {'  '.join(parts)}{change_str}")
    lines.append("")

    # Sub-community breakdown (top 20)
    if stats.get("by_sub_community"):
        lines.append(f"🏘 TOP SUB-COMMUNITIES")
        top_subs = list(stats["by_sub_community"].items())[:20]
        for sub, data in top_subs:
            # Find parent community for this sub
            parent = None
            for l in snapshot.get("listings", []):
                if l.get("sub_community") == sub:
                    parent = l.get("community")
                    break
            parent_str = f" ({parent})" if parent else ""
            sale_str = f"S:{data['sale']}" if data["sale"] else ""
            rent_str = f"R:{data['rent']}" if data["rent"] else ""
            type_parts = [s for s in [sale_str, rent_str] if s]
            lines.append(f"  {sub}{parent_str}: {data['total']} ({' | '.join(type_parts)})")
        lines.append("")

    # Changes section (if we have previous data)
    if changes:
        gaining = {k: v for k, v in changes["community_changes"].items() if v["change"] > 0}
        losing = {k: v for k, v in changes["community_changes"].items() if v["change"] < 0}

        if gaining:
            lines.append(f"📈 GAINING")
            for comm, data in list(gaining.items())[:5]:
                lines.append(f"  {comm}: +{data['change']} ({data['previous']}→{data['current']})")
            lines.append("")

        if losing:
            lines.append(f"📉 LOSING")
            for comm, data in list(losing.items())[:5]:
                lines.append(f"  {comm}: {data['change']} ({data['previous']}→{data['current']})")
            lines.append("")

        if changes["communities_gained"]:
            lines.append(f"🆕 New: {', '.join(changes['communities_gained'][:5])}")
        if changes["communities_lost"]:
            lines.append(f"❌ Exited: {', '.join(changes['communities_lost'][:5])}")
        if changes["communities_gained"] or changes["communities_lost"]:
            lines.append("")

    # Agent breakdown (top 10)
    agents = {k: v for k, v in stats["by_agent"].items() if k != "Unknown"}
    if agents:
        lines.append(f"👤 TOP AGENTS")
        for agent, data in list(agents.items())[:10]:
            lines.append(f"  {agent}: {data['total']} (S:{data['sale']} R:{data['rent']})")
        unknown = stats["by_agent"].get("Unknown", {})
        if unknown.get("total", 0) > 0:
            lines.append(f"  Unattributed: {unknown['total']}")
        lines.append("")

    # Footer
    lines.append(f"Credits: {snapshot.get('credits_used', '?')} | Scraped: {snapshot.get('total_scraped', '?')}/{snapshot.get('total_expected', '?')}")

    return "\n".join(lines)


if __name__ == "__main__":
    report = generate_report()
    print(report)
