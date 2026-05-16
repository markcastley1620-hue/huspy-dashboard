#!/usr/bin/env python3
"""
Daily Huspy tracker run.
Scrapes all listings, saves snapshot, syncs to Supabase, generates report.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import scrape_all_listings, save_snapshot
from market_scraper import scrape_market_data, save_market_data
from supabase_sync import transform_snapshot, upsert_to_supabase
from report import generate_report


def _fill_missing_agents(result):
    """Fetch agent names from detail pages for listings missing them."""
    import requests as req
    from bs4 import BeautifulSoup
    from concurrent.futures import ThreadPoolExecutor, as_completed
    API_KEY = os.environ.get('SCRAPINGBEE_API_KEY', 'QNG91WITJC8K7U39RMHTB7CAVQOUGTK8C09PPFJESMCYT2MNGJY19FLUQWDK3NABEC4PWPVF5HWI2CR0')

    listings = result['listings']
    missing = [(i, l) for i, l in enumerate(listings) if not l.get('agent') and l.get('url')]
    if not missing:
        print('  All agents attributed')
        return
    print(f'  Filling {len(missing)} missing agents from detail pages...')

    def fetch(idx_l):
        idx, l = idx_l
        try:
            r = req.get('https://app.scrapingbee.com/api/v1/', params={
                'api_key': API_KEY, 'url': f'https://www.bayut.com{l["url"]}',
                'stealth_proxy': 'true', 'country_code': 'ae',
            }, timeout=120)
            soup = BeautifulSoup(r.text, 'lxml')
            el = soup.find(attrs={'aria-label': 'Agent name'})
            return (idx, el.get_text(strip=True) if el else None)
        except:
            return (idx, None)

    found = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch, m): m for m in missing}
        for future in as_completed(futures):
            idx, name = future.result()
            if name:
                listings[idx]['agent'] = name
                found += 1
    print(f'  Recovered {found}/{len(missing)} agents')


def _enrich_supabase_with_market(date_str, snapshot, market_data):
    """Add market comparison data to the Supabase row."""
    import requests
    SUPABASE_URL = 'https://qwmjjrcdkrtoitwdsfhe.supabase.co'
    ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF3bWpqcmNka3J0b2l0d2RzZmhlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg2NTk3MjAsImV4cCI6MjA5NDIzNTcyMH0.FFnbLvx-JPZAYBwUv8remvNrwlH-AV0j5MovWw5UUkU'
    headers = {'apikey': ANON_KEY, 'Authorization': f'Bearer {ANON_KEY}', 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}

    resp = requests.get(
        f'{SUPABASE_URL}/rest/v1/market_intel_snapshots?snapshot_date=eq.{date_str}&select=data',
        headers={'apikey': ANON_KEY, 'Authorization': f'Bearer {ANON_KEY}'}, timeout=15,
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

    requests.patch(
        f'{SUPABASE_URL}/rest/v1/market_intel_snapshots?snapshot_date=eq.{date_str}',
        headers=headers, json={'data': existing}, timeout=15,
    )
    print('  ✓ Market enrichment pushed')


def run():
    print("⬡ NEXUS — Daily Huspy Run")
    print()

    # 1. Scrape listings
    result = scrape_all_listings(concurrency=10)
    path = save_snapshot(result)
    print(f"  Saved: {path}")
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
    print("Syncing to Supabase...")
    data = transform_snapshot(result)
    date_str = result["date"]
    success = upsert_to_supabase(date_str, data)
    # Enrich with market comparison
    if success:
        _enrich_supabase_with_market(date_str, result, market_result)
    print(f"  {'✓' if success else '✗'} Supabase sync")
    print()

    # 3. Generate report
    print("Generating report...")
    report = generate_report(date_str)
    print()

    return report


if __name__ == "__main__":
    report = run()
    print(report)
