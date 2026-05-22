#!/usr/bin/env python3
"""
Daily pipeline: XML feed → enriched JSON → dashboard build → GitHub Pages deploy.
No ScrapingBee needed for listings. Reuses latest Bayut scrape for spend/URLs.
"""

import os
import sys
import json
import glob
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from collections import Counter

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), '..', 'huspy-dashboard')
XML_URL = 'https://huspy.my.salesforce-sites.com/PropertiesXML'


def fetch_xml():
    """Download the Salesforce XML feed."""
    xml_path = os.path.join(DATA_DIR, 'xml_feed.xml')
    print(f"[1/5] Fetching XML feed...")
    result = subprocess.run(
        ['curl', '-sS', '--max-time', '120', XML_URL, '-o', xml_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ERROR: curl failed: {result.stderr}")
        return None
    size = os.path.getsize(xml_path)
    print(f"  Downloaded {size:,} bytes")
    # Verify it's complete XML
    with open(xml_path, 'r') as f:
        tail = f.read()[-50:]
    if '</response>' not in tail:
        print(f"  ERROR: XML appears truncated")
        return None
    return xml_path


def parse_xml(xml_path):
    """Parse XML into listings JSON."""
    print(f"[2/5] Parsing XML...")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    properties = root.findall('.//Property')

    listings = []
    for p in properties:
        agent = (p.findtext('Listing_Agent') or '').strip()
        purpose_raw = (p.findtext('Property_purpose') or '').strip()
        purpose = 'rent' if purpose_raw.lower() == 'rent' else 'sale'
        try: price = int(float(p.findtext('Price') or 0))
        except: price = 0
        beds = p.findtext('Bedrooms')
        try: beds = int(beds) if beds and beds.strip() else None
        except: beds = None
        try: baths = int(p.findtext('Bathrooms') or 0)
        except: baths = None
        try: size = int(float(p.findtext('Property_Size') or 0))
        except: size = 0

        listings.append({
            'ref': p.findtext('Property_Ref_No'),
            'sf_id': p.findtext('SF_id'),
            'permit': p.findtext('Permit_Number'),
            'status': p.findtext('Property_Status'),
            'purpose': purpose,
            'type': (p.findtext('Property_Type') or '').strip(),
            'size_sqft': size,
            'bedrooms': beds,
            'bathrooms': baths,
            'price': price,
            'rent_frequency': (p.findtext('Rent_Frequency') or '').strip() or None,
            'furnished': p.findtext('Furnished'),
            'off_plan': p.findtext('Off_plan') == 'Yes',
            'title': p.findtext('Property_Title'),
            'city': p.findtext('City'),
            'community': (p.findtext('Locality') or '').strip(),
            'sub_community': (p.findtext('Sub_Locality') or '').strip(),
            'tower': (p.findtext('Tower_Name') or '').strip(),
            'agent': agent,
            'agent_email': (p.findtext('Listing_Agent_Email') or '').strip(),
            'agent_phone': (p.findtext('Listing_Agent_Phone') or '').strip(),
            'last_updated': p.findtext('Last_Updated'),
            'portals': [pt.text for pt in p.findall('.//portal') if pt.text],
        })

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    sale = [l for l in listings if l['purpose'] == 'sale']
    rent = [l for l in listings if l['purpose'] == 'rent']
    agents = len(set(l['agent'] for l in listings if l['agent']))
    print(f"  {len(listings)} listings ({len(sale)} sale, {len(rent)} rent), {agents} agents")
    return {'date': today, 'source': 'salesforce_xml', 'total': len(listings), 'listings': listings}


def enrich_with_bayut(feed):
    """Cross-reference with latest Bayut scrape for spend status + URLs."""
    print(f"[3/5] Enriching with Bayut data...")
    # Find latest Bayut scrape
    bayut_files = sorted(glob.glob(os.path.join(DATA_DIR, '202[0-9]-[0-9][0-9]-[0-9][0-9].json')))
    if not bayut_files:
        print("  No Bayut scrape data found, skipping enrichment")
        for xl in feed['listings']:
            xl.update({'bayut_id': None, 'bayut_url': None, 'promo': None, 'trubroker': False, 'verified': False})
        return

    bayut = json.load(open(bayut_files[-1]))
    print(f"  Using Bayut scrape: {os.path.basename(bayut_files[-1])}")

    # Build lookup: title+price+purpose
    bayut_lookup = {}
    for bl in bayut['listings']:
        key = f"{bl.get('title','').strip().lower()}|{bl.get('price_num','')}|{bl.get('purpose','')}"
        if key not in bayut_lookup:
            bayut_lookup[key] = bl

    matched = 0
    for xl in feed['listings']:
        key = f"{(xl.get('title','') or '').strip().lower()}|{xl.get('price','')}|{xl.get('purpose','')}"
        bl = bayut_lookup.get(key)
        if bl:
            xl['bayut_id'] = bl.get('listing_id')
            xl['bayut_url'] = bl.get('url')
            xl['promo'] = bl.get('promo')
            xl['trubroker'] = bl.get('trubroker', False)
            xl['verified'] = bl.get('verified', False)
            matched += 1
        else:
            xl['bayut_id'] = None
            xl['bayut_url'] = None
            xl['promo'] = None
            xl['trubroker'] = False
            xl['verified'] = False

    print(f"  Matched {matched}/{len(feed['listings'])} ({matched*100//len(feed['listings'])}%) with Bayut URLs + spend")


def update_first_seen(feed):
    """Maintain first_seen.json — tracks earliest date each ref appeared."""
    fs_path = os.path.join(DATA_DIR, 'first_seen.json')
    if os.path.exists(fs_path):
        first_seen = json.load(open(fs_path))
    else:
        first_seen = {}
    today = feed['date']
    new_count = 0
    for l in feed['listings']:
        if l['ref'] not in first_seen:
            first_seen[l['ref']] = today
            new_count += 1
    with open(fs_path, 'w') as f:
        json.dump(first_seen, f)
    print(f"  first_seen.json: {len(first_seen)} refs tracked, {new_count} new today")
    return first_seen


def save_feed(feed):
    """Save enriched feed and daily snapshot."""
    print(f"[4/5] Saving data...")
    # Update first_seen registry
    first_seen = update_first_seen(feed)

    # Add listed_date to each listing in the feed
    for l in feed['listings']:
        l['listed_date'] = first_seen.get(l['ref'], feed['date'])

    feed_path = os.path.join(DATA_DIR, 'xml_feed.json')
    with open(feed_path, 'w') as f:
        json.dump(feed, f)

    # Save daily snapshot (refs only, for new listing detection)
    snap_path = os.path.join(DATA_DIR, f"xml_{feed['date']}.json")
    with open(snap_path, 'w') as f:
        json.dump({'date': feed['date'], 'listings': [{'ref': l['ref']} for l in feed['listings']]}, f)
    print(f"  Saved xml_feed.json + xml_{feed['date']}.json")


def build_and_deploy():
    """Build dashboard and push to GitHub Pages."""
    print(f"[5/5] Building dashboard and deploying...")
    result = subprocess.run(
        ['node', 'build_xml.js'],
        cwd=DASHBOARD_DIR, capture_output=True, text=True
    )
    print(f"  {result.stdout.strip()}")
    if result.returncode != 0:
        print(f"  BUILD ERROR: {result.stderr}")
        return False

    # Deploy via GitHub API
    token = os.environ.get('GH_TOKEN', '')
    if not token:
        # Try reading from git remote
        try:
            remote = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=DASHBOARD_DIR,
                                     capture_output=True, text=True).stdout.strip()
            if '@' in remote:
                token = remote.split(':')[1].split('@')[0] if '://' in remote else ''
                if not token:
                    import re
                    m = re.search(r'://[^:]+:([^@]+)@', remote)
                    token = m.group(1) if m else ''
        except:
            pass

    if not token:
        print("  No GitHub token, skipping deploy")
        return False

    import urllib.request
    repo = 'markcastley1620-hue/huspy-dashboard'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}

    # Get current SHA
    req = urllib.request.Request(
        f'https://api.github.com/repos/{repo}/contents/index.html?ref=gh-pages',
        headers=headers
    )
    sha = ''
    try:
        resp = urllib.request.urlopen(req)
        sha = json.loads(resp.read()).get('sha', '')
    except:
        pass

    # Upload
    import base64
    dist_path = os.path.join(DASHBOARD_DIR, 'dist', 'index.html')
    with open(dist_path, 'rb') as f:
        content = base64.b64encode(f.read()).decode()

    payload = json.dumps({
        'message': f'daily: {feed["date"]} — {feed["total"]} listings',
        'branch': 'gh-pages',
        'sha': sha,
        'content': content,
    }).encode()

    req = urllib.request.Request(
        f'https://api.github.com/repos/{repo}/contents/index.html',
        data=payload, headers={**headers, 'Content-Type': 'application/json'},
        method='PUT'
    )
    try:
        resp = urllib.request.urlopen(req)
        print(f"  Deployed to GitHub Pages ✓")
        return True
    except Exception as e:
        print(f"  Deploy failed: {e}")
        return False


if __name__ == '__main__':
    xml_path = fetch_xml()
    if not xml_path:
        sys.exit(1)

    feed = parse_xml(xml_path)
    enrich_with_bayut(feed)
    save_feed(feed)
    build_and_deploy()

    # Summary
    agents = Counter(l['agent'] for l in feed['listings'] if l['agent'])
    sale = sum(1 for l in feed['listings'] if l['purpose'] == 'sale')
    rent = sum(1 for l in feed['listings'] if l['purpose'] == 'rent')
    print(f"\n{'='*50}")
    print(f"DONE: {feed['total']} listings ({sale} sale, {rent} rent)")
    print(f"      {len(agents)} agents, 100% coverage")
    print(f"      Source: Salesforce XML (no ScrapingBee)")
    print(f"{'='*50}")
