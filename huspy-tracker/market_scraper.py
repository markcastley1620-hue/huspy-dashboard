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
    "Dubai Marina": "dubai-marina",
    "Business Bay": "business-bay",
    "Jumeirah Village Circle (JVC)": "jumeirah-village-circle-jvc",
    "Sobha Hartland": "sobha-hartland",
    "DAMAC Hills": "damac-hills-akoya-by-damac",
    "Palm Jumeirah": "palm-jumeirah",
    "Dubai Hills Estate": "dubai-hills-estate",
    "Al Furjan": "al-furjan",
    "DAMAC Hills 2 (Akoya by DAMAC)": "damac-hills-2-akoya-by-damac",
    "Downtown Dubai": "downtown-dubai",
    "Arabian Ranches 3": "arabian-ranches-3",
    "Town Square": "town-square",
    "Villanova": "villanova",
    "Jumeirah Lake Towers (JLT)": "jumeirah-lake-towers-jlt",
    "Dubai Creek Harbour": "dubai-creek-harbour",
    "Mudon": "mudon",
    "The Lakes": "the-lakes",
    "Arjan": "arjan",
    "Meydan": "meydan-city",
    "City Walk": "city-walk",
    "Jumeirah Beach Residence (JBR)": "jumeirah-beach-residence-jbr",
    "The Meadows": "the-meadows",
    "The Springs": "the-springs",
    "Motor City": "motor-city",
    "Mirdif": "mirdif",
    "Dubai South": "dubai-south",
    "Reem": "reem",
    "Discovery Gardens": "discovery-gardens",
    "International City": "international-city",
    "Arabian Ranches 2": "arabian-ranches-2",
    "Tilal Al Ghaf": "tilal-al-ghaf",
    "Dubailand": "dubailand",
    "Mohammed Bin Rashid City (MBR City)": "mohammed-bin-rashid-city",
    "Jebel Ali": "jebel-ali",
    "Jumeirah Golf Estates": "jumeirah-golf-estates",
    "Arabian Ranches": "arabian-ranches",
    "Dubai Media City": "dubai-media-city",
    "The Valley by Emaar": "the-valley-by-emaar",
    "Bluewaters Island": "bluewaters-island",
    "The Greens": "the-greens",
    "Palm Jebel Ali": "palm-jebel-ali",
    "Mina Rashid": "mina-rashid",
    "Sheikh Zayed Road": "sheikh-zayed-road",
    "Dubai Sports City": "dubai-sports-city",
    "The Views": "the-views",
    "Madinat Jumeirah Living": "madinat-jumeirah-living",
    "Emirates Hills": "emirates-hills",
    "Al Wasl": "al-wasl",
    "Jumeirah Village Triangle (JVT)": "jumeirah-village-triangle-jvt",
    "Dubai Investment Park (DIP)": "dubai-investment-park-dip",
    "Jumeirah Park": "jumeirah-park",
    "Green Community": "green-community",
    "Jumeirah Islands": "jumeirah-islands",
    "Dubai Maritime City": "dubai-maritime-city",
    "DAMAC Lagoons": "damac-lagoons",
    "Dubai Production City (IMPZ)": "dubai-production-city-impz",
    "Al Jaddaf": "al-jaddaf",
    "Dubai Harbour": "dubai-harbour",
    "Dubai Islands": "dubai-islands",
    "DIFC": "difc",
    "Al Barari": "al-barari",
    "Nad Al Sheba 1": "nad-al-sheba",
    "Bur Dubai": "bur-dubai",
    "Expo City": "expo-city",
    "Old Town": "old-town",
    "Dubai Festival City": "dubai-festival-city",
    "Sobha Hartland 2": "sobha-hartland-2",
    "La Mer": "la-mer-jumeirah",
    "Za'abeel 1": "zaabeel-1",
    "Dubai Studio City": "dubai-studio-city",
    "Dubai Internet City": "dubai-internet-city",
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

            # Get prices from listing cards
            for card in soup.find_all(attrs={"aria-label": "Listing"}):
                price_el = card.find(attrs={"aria-label": "Price"})
                if price_el:
                    p = price_el.get_text(strip=True).replace(",", "")
                    try:
                        all_prices.append(int(p))
                    except ValueError:
                        pass

        except Exception as e:
            print(f"    Error scraping {community} {purpose} p{page}: {e}")

    avg_price = int(sum(all_prices) / len(all_prices)) if all_prices else 0
    median_price = sorted(all_prices)[len(all_prices) // 2] if all_prices else 0

    return {
        "community": community,
        "purpose": "sale" if "sale" in purpose else "rent",
        "total_market": total_market,
        "sample_size": len(all_prices),
        "avg_price": avg_price,
        "median_price": median_price,
        "min_price": min(all_prices) if all_prices else 0,
        "max_price": max(all_prices) if all_prices else 0,
    }


def scrape_market_data(communities: dict = None, concurrency: int = 5) -> dict:
    """Scrape market pricing for all communities, both sale and rent."""
    if communities is None:
        communities = COMMUNITY_SLUGS

    print(f"⬡ Market Scraper — {len(communities)} communities × 2 purposes")
    start = time.time()

    tasks = []
    for comm, slug in communities.items():
        tasks.append((comm, slug, "for-sale"))
        tasks.append((comm, slug, "to-rent"))

    results = {"sale": {}, "rent": {}}

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {}
        for comm, slug, purpose in tasks:
            f = executor.submit(scrape_community_market, comm, slug, purpose, pages=2)
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
    credits = len(tasks) * 2 * 75  # 2 pages per task

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
