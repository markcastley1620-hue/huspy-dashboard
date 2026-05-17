"""
Market-wide pricing scraper.
Scrapes Bayut search pages for each community to get total market listings and avg prices.
Used to compare Huspy's pricing vs the broader market.
"""

import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

API_KEY = os.environ.get(
    "SCRAPINGBEE_API_KEY",
    "QNG91WITJC8K7U39RMHTB7CAVQOUGTK8C09PPFJESMCYT2MNGJY19FLUQWDK3NABEC4PWPVF5HWI2CR0"
)

# Community name → Bayut URL slug mapping
COMMUNITY_SLUGS = {
    "Al Barari": "al-barari",
    "Al Barsha": "al-barsha",
    "Al Furjan": "al-furjan",
    "Al Jaddaf": "al-jaddaf",
    "Al Kifaf": "al-kifaf",
    "Al Satwa": "al-satwa",
    "Al Wasl": "al-wasl",
    "Arabian Ranches": "arabian-ranches",
    "Arabian Ranches 2": "arabian-ranches-2",
    "Arabian Ranches 3": "arabian-ranches-3",
    "Arjan": "arjan",
    "Barsha Heights (Tecom)": "barsha-heights-tecom",
    "Bluewaters Island": "bluewaters-island",
    "Bur Dubai": "bur-dubai",
    "Business Bay": "business-bay",
    "City Walk": "city-walk",
    "City of Arabia": "city-of-arabia",
    "DAMAC Hills": "damac-hills-akoya-by-damac",
    "DAMAC Hills 2 (Akoya by DAMAC)": "damac-hills-2-akoya-by-damac",
    "DAMAC Lagoons": "damac-lagoons",
    "DIFC": "difc",
    "Discovery Gardens": "discovery-gardens",
    "District 11": "district-11",
    "District 7": "district-7",
    "District One": "district-one",
    "Downtown Dubai": "downtown-dubai",
    "Dubai Creek Harbour": "dubai-creek-harbour",
    "Dubai Festival City": "dubai-festival-city",
    "Dubai Harbour": "dubai-harbour",
    "Dubai Hills Estate": "dubai-hills-estate",
    "Dubai Industrial City": "dubai-industrial-city",
    "Dubai Internet City": "dubai-internet-city",
    "Dubai Investment Park (DIP)": "dubai-investment-park-dip",
    "Dubai Islands": "dubai-islands",
    "Dubai Land Residence Complex (DLRC)": "dubai-land-residence-complex-dlrc",
    "Dubai Marina": "dubai-marina",
    "Dubai Maritime City": "dubai-maritime-city",
    "Dubai Media City": "dubai-media-city",
    "Dubai Production City (IMPZ)": "dubai-production-city-impz",
    "Dubai South": "dubai-south",
    "Dubai Sports City": "dubai-sports-city",
    "Dubai Studio City": "dubai-studio-city",
    "Dubailand": "dubailand",
    "Emaar Beachfront": "emaar-beachfront",
    "Emaar South": "emaar-south",
    "Emirates Hills": "emirates-hills",
    "Expo City": "expo-city",
    "Falcon City of Wonders": "falcon-city-of-wonders",
    "Green Community": "green-community",
    "Haven by Aldar": "haven-by-aldar",
    "International City": "international-city",
    "JVT District 2": "jvt-district-2",
    "Jebel Ali": "jebel-ali",
    "Jumeirah Beach Residence (JBR)": "jumeirah-beach-residence-jbr",
    "Jumeirah Golf Estates": "jumeirah-golf-estates",
    "Jumeirah Islands": "jumeirah-islands",
    "Jumeirah Lake Towers (JLT)": "jumeirah-lake-towers-jlt",
    "Jumeirah Park": "jumeirah-park",
    "Jumeirah Village Circle (JVC)": "jumeirah-village-circle-jvc",
    "Jumeirah Village Triangle (JVT)": "jumeirah-village-triangle-jvt",
    "La Mer": "la-mer-jumeirah",
    "Madinat Jumeirah Living": "madinat-jumeirah-living",
    "Meydan": "meydan-city",
    "Meydan Avenue": "meydan-avenue",
    "Meydan Horizon": "meydan-horizon",
    "Meydan One": "meydan-one",
    "Midtown": "midtown",
    "Mina Rashid": "mina-rashid",
    "Mirdif": "mirdif",
    "Mohammed Bin Rashid City (MBR City)": "mohammed-bin-rashid-city",
    "Motor City": "motor-city",
    "Mudon": "mudon",
    "Nad Al Sheba 1": "nad-al-sheba",
    "Old Town": "old-town",
    "Palm Jebel Ali": "palm-jebel-ali",
    "Palm Jumeirah": "palm-jumeirah",
    "Park Heights": "park-heights",
    "Reem": "reem",
    "Residential District": "residential-district",
    "Serena": "serena",
    "Sheikh Zayed Road": "sheikh-zayed-road",
    "Sobha Hartland": "sobha-hartland",
    "Sobha Hartland 2": "sobha-hartland-2",
    "The Greens": "the-greens",
    "The Lakes": "the-lakes",
    "The Meadows": "the-meadows",
    "The Springs": "the-springs",
    "The Valley by Emaar": "the-valley-by-emaar",
    "The Views": "the-views",
    "The Villa": "the-villa",
    "Tilal Al Ghaf": "tilal-al-ghaf",
    "Town Square": "town-square",
    "Uptown Motor City": "uptown-motor-city",
    "Villanova": "villanova",
    "Wasl Gate": "wasl-gate",
    "Za'abeel 1": "zaabeel-1",
}

# Sub-locations that don't have their own Bayut search page.
# Map them to their parent community for market comparison.
SUB_TO_PARENT = {
    "Villanova": "Dubailand",
    "Emaar Beachfront": "Dubai Marina",
    "City Walk": "Al Wasl",
    "Meydan One": "Meydan",
    "Meydan Horizon": "Meydan",
    "Meydan Avenue": "Meydan",
    "La Mer": "Palm Jumeirah",
    "Port de La Mer": "Palm Jumeirah",
    "Madinat Jumeirah Living": "Palm Jumeirah",
    "Barsha Heights (Tecom)": "Al Barsha",
    "Za'abeel 1": "Downtown Dubai",
    "JVC District 10": "Jumeirah Village Circle (JVC)",
    "JVC District 11": "Jumeirah Village Circle (JVC)",
    "JVC District 12": "Jumeirah Village Circle (JVC)",
    "JVC District 13": "Jumeirah Village Circle (JVC)",
    "JVC District 15": "Jumeirah Village Circle (JVC)",
    "District 11": "Mohammed Bin Rashid City (MBR City)",
    "District One": "Mohammed Bin Rashid City (MBR City)",
    "District 7": "Jumeirah Village Circle (JVC)",
    "Park Heights": "Dubai Hills Estate",
    "Uptown Motor City": "Motor City",
    "Golf Promenade": "DAMAC Hills",
    "Golf Town": "DAMAC Hills",
    "Residential District": "Dubai South",
    "Emaar South": "Dubai South",
    "Central Park": "Dubai Investment Park (DIP)",
    "Midtown": "Dubai Production City (IMPZ)",
    "Opera District": "Downtown Dubai",
    "Wasl Gate": "Al Wasl",
    "Sobha Hartland 2": "Sobha Hartland",
    "The Pulse": "Dubai South",
    "Azizi Riviera": "Meydan",
    "City of Arabia": "Dubailand",
    "Dubai Land Residence Complex (DLRC)": "Dubailand",
    "JVT District 2": "Jumeirah Village Triangle (JVT)",
    "Serena": "Dubailand",
    "Haven by Aldar": "Dubailand",
    "Falcon City of Wonders": "Dubailand",
    "Al Satwa": "Bur Dubai",
    "The Villa": "Dubailand",
    "Al Kifaf": "Bur Dubai",
    "Dubai Internet City": "Dubai Media City",
}


def scrape_community_market(community: str, slug: str, purpose: str, pages: int = 2) -> dict:
    """Scrape market data for a community. purpose = 'for-sale' or 'for-rent'."""
    all_prices = []
    all_by_bed = {}
    all_by_bed_type = {}
    all_by_sub = {}       # sub_community|bed|type -> [prices]
    all_by_sub_bed = {}   # sub_community|bed -> [prices]
    total_market = 0

    for page in range(1, pages + 1):
        url = f"https://www.bayut.com/{purpose}/property/dubai/{slug}/"
        if page > 1:
            url += f"?page={page}"

        try:
            resp = requests.get("https://app.scrapingbee.com/api/v1/", params={
                "api_key": API_KEY,
                "url": url,
                "stealth_proxy": "true",
                "country_code": "ae",
            }, timeout=120)

            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "lxml")

            # Get total count (first page only)
            if page == 1:
                text = soup.get_text()
                # Match "X Properties" with at least one space to avoid false positives
                m = re.search(r"([\d,]+)\s+Properties", text)
                if m:
                    total_market = int(m.group(1).replace(",", ""))

            # Get prices, beds, and type from listing cards
            for card in soup.find_all(attrs={"aria-label": "Listing"}):
                price_el = card.find(attrs={"aria-label": "Price"})
                if not price_el:
                    continue
                p = price_el.get_text(strip=True).replace(",", "")
                try:
                    price_val = int(p)
                except ValueError:
                    continue
                all_prices.append(price_val)

                # Extract beds
                beds_el = card.find(attrs={"aria-label": "Beds"})
                beds_text = beds_el.get_text(strip=True) if beds_el else ""
                beds = None
                if "Studio" in beds_text:
                    beds = 0
                else:
                    bm = re.search(r"(\d+)", beds_text)
                    if bm:
                        beds = int(bm.group(1))

                # Extract type
                type_el = card.find(attrs={"aria-label": "Type"})
                ptype = type_el.get_text(strip=True) if type_el else None

                # Extract sub-community from location
                loc_el = card.find(attrs={"aria-label": "Location"})
                loc_text = loc_el.get_text(strip=True) if loc_el else ""
                loc_parts = [p.strip() for p in loc_text.split(",") if p.strip()]
                sub_comm = None
                if len(loc_parts) >= 3:
                    sub_comm = loc_parts[0]  # First part is usually tower/sub-community
                elif len(loc_parts) == 2:
                    sub_comm = loc_parts[0]

                if beds is not None:
                    bed_key = str(beds) if beds > 0 else "Studio"
                    all_by_bed.setdefault(bed_key, []).append(price_val)
                    if ptype:
                        all_by_bed_type.setdefault(f"{bed_key}|{ptype}", []).append(price_val)
                    # Sub-community level grouping
                    if sub_comm and ptype:
                        all_by_sub.setdefault(f"{sub_comm}|{bed_key}|{ptype}", []).append(price_val)
                    if sub_comm:
                        all_by_sub_bed.setdefault(f"{sub_comm}|{bed_key}", []).append(price_val)

        except Exception as e:
            print(f"    Error scraping {community} {purpose} p{page}: {e}")

    from statistics import median as stat_median
    avg_price = int(sum(all_prices) / len(all_prices)) if all_prices else 0
    median_price = sorted(all_prices)[len(all_prices) // 2] if all_prices else 0

    # Per-bed market medians + individual prices for ranking
    by_bed = {}
    for bed_key, prices in all_by_bed.items():
        by_bed[bed_key] = {
            "count": len(prices),
            "avg_price": int(sum(prices) / len(prices)),
            "median_price": int(stat_median(prices)),
            "min_price": min(prices),
            "max_price": max(prices),
            "prices": sorted(prices),
        }

    # Per-bed+type market medians + individual prices for ranking
    by_bed_type = {}
    for bt_key, prices in all_by_bed_type.items():
        by_bed_type[bt_key] = {
            "count": len(prices),
            "avg_price": int(sum(prices) / len(prices)),
            "median_price": int(stat_median(prices)),
            "prices": sorted(prices),
        }

    # Per sub-community+bed+type
    by_sub = {}
    for key, prices in all_by_sub.items():
        by_sub[key] = {
            "count": len(prices),
            "median_price": int(stat_median(prices)),
            "prices": sorted(prices),
        }
    by_sub_bed = {}
    for key, prices in all_by_sub_bed.items():
        by_sub_bed[key] = {
            "count": len(prices),
            "median_price": int(stat_median(prices)),
            "prices": sorted(prices),
        }

    return {
        "community": community,
        "purpose": "sale" if "sale" in purpose else "rent",
        "total_market": total_market,
        "sample_size": len(all_prices),
        "avg_price": avg_price,
        "median_price": median_price,
        "min_price": min(all_prices) if all_prices else 0,
        "max_price": max(all_prices) if all_prices else 0,
        "by_bed": by_bed,
        "by_bed_type": by_bed_type,
        "by_sub": by_sub,
        "by_sub_bed": by_sub_bed,
    }


def scrape_market_data(communities: dict = None, concurrency: int = 5) -> dict:
    """Scrape market pricing for all communities, both sale and rent."""
    if communities is None:
        communities = COMMUNITY_SLUGS

    print(f"⬡ Market Scraper — {len(communities)} communities × 2 purposes")
    start = time.time()

    pages_per = 4  # 4 pages = ~96 sample listings per community for better sub-community coverage
    tasks = []
    for comm, slug in communities.items():
        tasks.append((comm, slug, "for-sale"))
        tasks.append((comm, slug, "to-rent"))

    results = {"sale": {}, "rent": {}}

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {}
        for comm, slug, purpose in tasks:
            f = executor.submit(scrape_community_market, comm, slug, purpose, pages=pages_per)
            futures[f] = (comm, purpose)

        completed = 0
        for future in as_completed(futures):
            completed += 1
            comm, purpose = futures[future]
            data = future.result()
            purpose_key = data["purpose"]
            results[purpose_key][comm] = data

            if completed % 10 == 0:
                print(f"  Progress: {completed}/{len(tasks)}")

    elapsed = time.time() - start
    credits = len(tasks) * pages_per * 75

    results["meta"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "communities_scraped": len(communities),
        "credits_used": credits,
        "elapsed_seconds": round(elapsed),
    }

    print(f"\n  ✓ Done in {elapsed:.0f}s | ~{credits} credits")
    return results


def save_market_data(data: dict, data_dir: str = "data") -> str:
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, f"market_{data['meta']['date']}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


if __name__ == "__main__":
    data = scrape_market_data()
    path = save_market_data(data)
    print(f"  Saved to {path}")


# Sub-community slug mapping for direct Bayut scraping
# Format: (community_slug, sub_community_slug) -> allows URL construction
# Bayut pattern: bayut.com/for-sale/apartments/dubai/{community_slug}/{sub_slug}/

# Short slugs for type-specific Bayut URLs (townhouses/villas pages use these)
SHORT_SLUGS = {
    "DAMAC Hills": "damac-hills",
    "DAMAC Hills 2 (Akoya by DAMAC)": "damac-hills-2",
}


FULL_PATH_SLUGS = {
    "Al Kifaf": "bur-dubai/al-kifaf",
    "Al Satwa": "bur-dubai/al-satwa",
    "Barsha Heights (Tecom)": "al-barsha/barsha-heights-tecom",
    "City Walk": "al-wasl/city-walk",
    "City of Arabia": "dubailand/city-of-arabia",
    "District 11": "mohammed-bin-rashid-city/district-11",
    "District 7": "jumeirah-village-circle-jvc/district-7",
    "District One": "mohammed-bin-rashid-city/district-one",
    "Dubai Internet City": "dubai-media-city/dubai-internet-city",
    "Dubai Land Residence Complex (DLRC)": "dubailand/dubai-land-residence-complex-dlrc",
    "Emaar Beachfront": "dubai-marina/emaar-beachfront",
    "Emaar South": "dubai-south/emaar-south",
    "Falcon City of Wonders": "dubailand/falcon-city-of-wonders",
    "Haven by Aldar": "dubailand/haven-by-aldar",
    "JVT District 2": "jumeirah-village-triangle-jvt/jvt-district-2",
    "La Mer": "palm-jumeirah/la-mer-jumeirah",
    "Madinat Jumeirah Living": "palm-jumeirah/madinat-jumeirah-living",
    "Meydan Avenue": "meydan-city/meydan-avenue",
    "Meydan Horizon": "meydan-city/meydan-horizon",
    "Meydan One": "meydan-city/meydan-one",
    "Midtown": "dubai-production-city-impz/midtown",
    "Park Heights": "dubai-hills-estate/park-heights",
    "Residential District": "dubai-south/residential-district",
    "Serena": "dubailand/serena",
    "Sobha Hartland 2": "sobha-hartland/sobha-hartland-2",
    "The Villa": "dubailand/the-villa",
    "Uptown Motor City": "motor-city/uptown-motor-city",
    "Villanova": "dubailand/villanova",
    "Wasl Gate": "al-wasl/wasl-gate",
    "Za'abeel 1": "downtown-dubai/zaabeel-1",
}

def _slugify(name):
    """Convert a sub-community name to a Bayut URL slug."""
    import re
    s = name.lower().strip()
    s = re.sub(r'[()]', '', s)
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = s.strip('-')
    return s


def scrape_sub_community_market(community_slug, sub_slug, purpose, pages=2):
    """Scrape market data for a specific sub-community."""
    from statistics import median as stat_median
    all_prices = []
    by_bed = {}
    by_bed_type = {}

    for page in range(1, pages + 1):
        url = f"https://www.bayut.com/{purpose}/property/dubai/{community_slug}/{sub_slug}/"
        if page > 1:
            url += f"?page={page}"
        try:
            resp = requests.get("https://app.scrapingbee.com/api/v1/", params={
                "api_key": API_KEY, "url": url, "stealth_proxy": "true", "country_code": "ae",
            }, timeout=120)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for card in soup.find_all(attrs={"aria-label": "Listing"}):
                price_el = card.find(attrs={"aria-label": "Price"})
                if not price_el:
                    continue
                try:
                    price_val = int(price_el.get_text(strip=True).replace(",", ""))
                except ValueError:
                    continue
                all_prices.append(price_val)
                beds_el = card.find(attrs={"aria-label": "Beds"})
                beds_text = beds_el.get_text(strip=True) if beds_el else ""
                beds = None
                if "Studio" in beds_text:
                    beds = 0
                else:
                    bm = re.search(r"(\d+)", beds_text)
                    if bm:
                        beds = int(bm.group(1))
                type_el = card.find(attrs={"aria-label": "Type"})
                ptype = type_el.get_text(strip=True) if type_el else None
                if beds is not None:
                    bed_key = str(beds) if beds > 0 else "Studio"
                    by_bed.setdefault(bed_key, []).append(price_val)
                    if ptype:
                        by_bed_type.setdefault(f"{bed_key}|{ptype}", []).append(price_val)
        except Exception as e:
            print(f"    Error scraping sub-comm {sub_slug}: {e}")

    if not all_prices:
        return None

    result_by_bed = {}
    for bk, prices in by_bed.items():
        result_by_bed[bk] = {
            "count": len(prices), "median_price": int(stat_median(prices)), "prices": sorted(prices),
        }
    result_by_bt = {}
    for btk, prices in by_bed_type.items():
        result_by_bt[btk] = {
            "count": len(prices), "median_price": int(stat_median(prices)), "prices": sorted(prices),
        }
    return {
        "sample_size": len(all_prices),
        "median_price": int(stat_median(all_prices)),
        "by_bed": result_by_bed,
        "by_bed_type": result_by_bt,
    }


def scrape_important_subs(snapshot, community_slugs, market_data, concurrency=10, min_listings=3):
    """Scrape sub-community market data for sub-communities with enough Huspy listings."""
    from collections import Counter

    sub_counts = Counter()
    for l in snapshot.get('listings', []):
        if l.get('sub_community') and l.get('community'):
            sub_counts[(l['community'], l['sub_community'], l['purpose'])] += 1

    important = [(k, v) for k, v in sub_counts.items() if v >= min_listings]
    if not important:
        print("  No important sub-communities to scrape")
        return market_data

    print(f"  Scraping {len(important)} important sub-communities...")

    tasks = []
    for (comm, sub, purpose), count in important:
        comm_slug = FULL_PATH_SLUGS.get(comm) or community_slugs.get(comm)
        if not comm_slug:
            continue
        sub_slug = _slugify(sub)
        bayut_purpose = "for-sale" if purpose == "sale" else "to-rent"
        tasks.append((comm, sub, purpose, comm_slug, sub_slug, bayut_purpose))

    credits = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        def _fetch(task):
            comm, sub, purpose, comm_slug, sub_slug, bayut_purpose = task
            return (comm, sub, purpose, scrape_sub_community_market(comm_slug, sub_slug, bayut_purpose, pages=2))

        futures = {executor.submit(_fetch, t): t for t in tasks}
        done = 0
        found = 0
        for future in as_completed(futures):
            comm, sub, purpose, result = future.result()
            done += 1
            credits += 2 * 75
            if result and result['sample_size'] > 0:
                found += 1
                # Inject into market_data
                comm_data = market_data.setdefault(purpose, {}).setdefault(comm, {})
                for bk, bv in result.get('by_bed', {}).items():
                    sub_key = f"{sub}|{bk}"
                    comm_data.setdefault('by_sub_bed', {})[sub_key] = bv
                for btk, btv in result.get('by_bed_type', {}).items():
                    sub_key = f"{sub}|{btk}"
                    comm_data.setdefault('by_sub', {})[sub_key] = btv
            if done % 20 == 0:
                print(f"    Sub-comm progress: {done}/{len(tasks)} ({found} found)")

    print(f"  Sub-communities scraped: {found}/{len(tasks)} found data | ~{credits} credits")
    return market_data
