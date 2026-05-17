#!/usr/bin/env python3
"""
Daily Huspy tracker run.
Scrapes all listings, saves snapshot, syncs to Supabase, generates report.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import scrape_all_listings, save_snapshot
from market_scraper import scrape_market_data, save_market_data, scrape_important_subs, COMMUNITY_SLUGS
from supabase_sync import transform_snapshot, upsert_to_supabase
from report import generate_report
from validator import validate_snapshot, print_report
from scrape_runs import start_run, complete_run


def _fill_missing_agents(result):
    """Fetch agent names and DOM from detail pages for listings missing them."""
    import re as _re
    import requests as req
    from datetime import datetime as _dt
    from bs4 import BeautifulSoup
    from concurrent.futures import ThreadPoolExecutor, as_completed
    API_KEY = os.environ.get('SCRAPINGBEE_API_KEY', 'QNG91WITJC8K7U39RMHTB7CAVQOUGTK8C09PPFJESMCYT2MNGJY19FLUQWDK3NABEC4PWPVF5HWI2CR0')

    listings = result['listings']
    # Fetch detail pages for: missing agent OR missing DOM
    need_detail = [(i, l) for i, l in enumerate(listings)
                   if l.get('url') and (not l.get('agent') or l.get('dom') is None)]
    if not need_detail:
        print('  All agents + DOM filled')
        return
    print(f'  Fetching {len(need_detail)} detail pages (agent + DOM)...')

    def fetch(idx_l):
        idx, l = idx_l
        try:
            r = req.get('https://app.scrapingbee.com/api/v1/', params={
                'api_key': API_KEY, 'url': f'https://www.bayut.com{l["url"]}',
                'stealth_proxy': 'true', 'country_code': 'ae',
            }, timeout=120)
            soup = BeautifulSoup(r.text, 'lxml')
            agent_el = soup.find(attrs={'aria-label': 'Agent name'})
            agent = agent_el.get_text(strip=True) if agent_el else None
            listed_date = None
            dom = None
            text = soup.get_text()
            date_match = _re.search(r'(?:Listed|Added)\s+(?:on\s+)?(\d+)\w*\s+(?:of\s+)?(\w+)\s+(\d{4})', text)
            if date_match:
                try:
                    day, month, year = date_match.group(1), date_match.group(2), date_match.group(3)
                    listed_date = _dt.strptime(f'{day} {month} {year}', '%d %B %Y').strftime('%Y-%m-%d')
                    dom = (_dt.utcnow() - _dt.strptime(listed_date, '%Y-%m-%d')).days
                except (ValueError, Exception):
                    pass
            return (idx, agent, listed_date, dom)
        except:
            return (idx, None, None, None)

    agents_found = 0
    doms_found = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch, m): m for m in need_detail}
        done = 0
        for future in as_completed(futures):
            idx, agent, listed_date, dom = future.result()
            done += 1
            if agent and not listings[idx].get('agent'):
                listings[idx]['agent'] = agent
                agents_found += 1
            if dom is not None and listings[idx].get('dom') is None:
                listings[idx]['dom'] = dom
                listings[idx]['listed_date'] = listed_date
                doms_found += 1
            if done % 50 == 0:
                print(f'    Progress: {done}/{len(need_detail)}')
    print(f'  Recovered {agents_found} agents, {doms_found} DOMs from {len(need_detail)} detail pages')


def _enrich_supabase_with_market(date_str, snapshot, market_data):
    """Add market comparison data to the Supabase row."""
    import requests
    SUPABASE_URL = 'https://qwmjjrcdkrtoitwdsfhe.supabase.co'
    ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF3bWpqcmNka3J0b2l0d2RzZmhlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg2NTk3MjAsImV4cCI6MjA5NDIzNTcyMH0.FFnbLvx-JPZAYBwUv8remvNrwlH-AV0j5MovWw5UUkU'
    headers = {'apikey': ANON_KEY, 'Authorization': f'Bearer {ANON_KEY}', 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}

    resp = requests.get(
        f'{SUPABASE_URL}/rest/v1/market_intel_snapshots?snapshot_date=eq.{date_str}&select=data',
        headers={'apikey': ANON_KEY, 'Authorization': f'Bearer {ANON_KEY}'}, timeout=60,
    )
    if resp.status_code != 200 or not resp.json():
        return
    existing = resp.json()[0]['data']

    # Set real Dubai market totals (from top-level Bayut search)
    # These are scraped separately and stored in market_data meta
    existing.setdefault('sale', {})['dubai_market_total'] = 117476
    existing.setdefault('rent', {})['dubai_market_total'] = 109412

    from market_scraper import SUB_TO_PARENT

    for purpose, mkt_key in [('sale', 'sale'), ('rent', 'rent')]:
        mkt = market_data.get(mkt_key, {})
        for comm, data in existing.get(purpose, {}).get('by_community', {}).items():
            m = mkt.get(comm, {})
            mt = m.get('total_market')
            # If no market data, try parent community
            if (not mt or mt <= 0) and comm in SUB_TO_PARENT:
                parent = SUB_TO_PARENT[comm]
                m = mkt.get(parent, {})
                mt = m.get('total_market')
                if mt and mt > 0:
                    data['parent_community'] = parent
            data['market_total'] = mt if mt and mt > 0 else None
            data['market_avg_price'] = m.get('avg_price') if mt and mt > 0 else None
            if mt and mt > 0 and data.get('count'):
                data['share_pct'] = round(data['count'] / mt * 100, 2)
            else:
                data['share_pct'] = None
            if m.get('avg_price') and data.get('avg_price') and mt and mt > 0:
                data['price_vs_market_pct'] = round(((data['avg_price'] - m['avg_price']) / m['avg_price']) * 100, 1)
            else:
                data['price_vs_market_pct'] = None

            # Enrich sub-communities with SUB-COMMUNITY specific market data
            by_sub_mkt = m.get('by_sub', {})       # sub|bed|type -> {count, median_price, prices}
            by_sub_bed_mkt = m.get('by_sub_bed', {})  # sub|bed -> {count, median_price, prices}
            by_bed_mkt = m.get('by_bed', {})
            by_bed_type_mkt = m.get('by_bed_type', {})

            for sc_name, sc_data in data.get('sub_communities', {}).items():
                sc_beds = sc_data.get('beds', {})

                # Try to find sub-community specific market data
                # Sum up all by_sub_bed entries for this sub-community
                sc_market_count = 0
                sc_weighted_sum = 0
                sc_total_n = 0
                found_sub_data = False

                for bed_key, bed_info in sc_beds.items():
                    bed_count = bed_info.get('count', 0) if isinstance(bed_info, dict) else bed_info
                    bk = 'Studio' if bed_key in ('0', 'Studio') else bed_key
                    mkt_price = None
                    mkt_count = 0

                    # 1. Try sub-community + bed + type (from by_sub)
                    for sub_k, sub_v in by_sub_mkt.items():
                        parts = sub_k.split('|')
                        if len(parts) >= 2 and parts[1] == bk:
                            sub_name = parts[0]
                            # Fuzzy match sub-community name
                            if (sub_name.lower() == sc_name.lower() or
                                sc_name.lower() in sub_name.lower() or
                                sub_name.lower() in sc_name.lower()):
                                mkt_price = sub_v.get('median_price')
                                mkt_count += sub_v.get('count', 0)
                                found_sub_data = True
                                break

                    # 2. Try sub-community + bed (from by_sub_bed)
                    if not mkt_price:
                        for sub_k, sub_v in by_sub_bed_mkt.items():
                            parts = sub_k.split('|')
                            if len(parts) == 2 and parts[1] == bk:
                                sub_name = parts[0]
                                if (sub_name.lower() == sc_name.lower() or
                                    sc_name.lower() in sub_name.lower() or
                                    sub_name.lower() in sc_name.lower()):
                                    mkt_price = sub_v.get('median_price')
                                    mkt_count = sub_v.get('count', 0)
                                    found_sub_data = True
                                    break

                    # 3. Fallback to community + bed + type
                    if not mkt_price:
                        for bt_k, bt_v in by_bed_type_mkt.items():
                            if bt_k.startswith(f"{bk}|") and bt_v.get('median_price'):
                                mkt_price = bt_v['median_price']
                                mkt_count = bt_v.get('count', 0)
                                break

                    # 4. Fallback to community + bed
                    if not mkt_price and bk in by_bed_mkt:
                        mkt_price = by_bed_mkt[bk].get('median_price')
                        mkt_count = by_bed_mkt[bk].get('count', 0)

                    if mkt_price and bed_count:
                        sc_weighted_sum += mkt_price * bed_count
                        sc_total_n += bed_count
                        sc_market_count += mkt_count
                        if isinstance(bed_info, dict):
                            bed_info['market_avg_price'] = mkt_price

                if sc_total_n > 0:
                    sc_data['market_avg_price'] = int(sc_weighted_sum / sc_total_n)
                    # Use sub-community specific count if found, else None (not community total)
                    sc_data['market_count'] = sc_market_count if found_sub_data else None
                else:
                    sc_data['market_avg_price'] = None
                    sc_data['market_count'] = None

    requests.patch(
        f'{SUPABASE_URL}/rest/v1/market_intel_snapshots?snapshot_date=eq.{date_str}',
        headers=headers, json={'data': existing}, timeout=15,
    )
    print('  ✓ Market enrichment pushed')


def run():
    print("⬡ NEXUS — Daily Huspy Run")
    print()

    run_record = start_run("daily_full", "Automated daily run")
    run_id = run_record["run_id"]
    print(f"  Run ID: {run_id}")

    # 1. Scrape listings
    result = scrape_all_listings(concurrency=3)
    path = save_snapshot(result)
    print(f"  Saved: {path}")
    print()

    # 1a. Validate snapshot
    print("Validating...")
    registry = set(COMMUNITY_SLUGS.keys())
    audit = validate_snapshot(result["listings"], community_registry=registry)
    print_report(audit)
    result["listings"] = audit["accepted_records"]  # Only use validated records
    result["total_scraped"] = len(audit["accepted_records"])
    save_snapshot(result)
    print()

    # 1b. Fill missing agents from detail pages
    _fill_missing_agents(result)
    save_snapshot(result)
    print()

    # 2. Market comparison scrape
    print("Scraping market data...")
    market_result = scrape_market_data(concurrency=8)
    save_market_data(market_result)
    print()

    # 3. Sync to Supabase (with market data enrichment)
    # 2b. Sub-community market scrape for important sub-communities
    print("Scraping important sub-communities...")
    market_result = scrape_important_subs(result, COMMUNITY_SLUGS, market_result, concurrency=10)
    save_market_data(market_result)
    print()

    print("Syncing to Supabase...")
    data = transform_snapshot(result)
    date_str = result["date"]
    success = upsert_to_supabase(date_str, data)
    # Enrich with market comparison
    if success:
        _enrich_supabase_with_market(date_str, result, market_result)
    print(f"  {'✓' if success else '✗'} Supabase sync")
    print()

    # 4. Generate report
    print("Generating report...")
    report = generate_report(date_str)
    print()

    complete_run(run_id, status="success",
        records_scraped=audit["total"],
        records_accepted=audit["accepted"],
        records_rejected=audit["rejected"],
    )
    print(f"  Run {run_id} complete: {audit['accepted']} accepted, {audit['rejected']} rejected")

    return report


if __name__ == "__main__":
    report = run()
    print(report)
