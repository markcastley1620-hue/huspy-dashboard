"""
Huspy Dubai listings scraper.
Scrapes all listings from Bayut company page with concurrent pagination.
"""

import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

API_KEY = os.environ.get(
    "SCRAPINGBEE_API_KEY",
    "QNG91WITJC8K7U39RMHTB7CAVQOUGTK8C09PPFJESMCYT2MNGJY19FLUQWDK3NABEC4PWPVF5HWI2CR0"
)

COMPANY_URL = "https://www.bayut.com/companies/huspy-dubai-101139/"


def scrape_page(page: int, max_retries: int = 3) -> tuple[int, str]:
    """Fetch a single page. Returns (page_num, html)."""
    url = f"{COMPANY_URL}?page={page}" if page > 1 else COMPANY_URL

    for attempt in range(max_retries):
        try:
            resp = requests.get("https://app.scrapingbee.com/api/v1/", params={
                "api_key": API_KEY,
                "url": url,
                "stealth_proxy": "true",
                "country_code": "ae",
            }, timeout=150)
            resp.raise_for_status()
            return (page, resp.text)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                print(f"  ✗ Page {page} failed: {e}")
                return (page, "")


def parse_listing_card(card) -> dict | None:
    """Parse a listing card using ARIA labels."""
    def get_aria(label):
        el = card.find(attrs={"aria-label": label})
        return el.get_text(strip=True) if el else None

    price_text = get_aria("Price")
    if not price_text:
        return None

    price_num = int(price_text.replace(",", "")) if price_text else None
    frequency = get_aria("Frequency")
    purpose = "rent" if frequency else "sale"

    beds_text = get_aria("Beds")
    beds = None
    if beds_text:
        if "Studio" in beds_text:
            beds = 0
        else:
            m = re.search(r"(\d+)", beds_text)
            if m:
                beds = int(m.group(1))
    # Apartments with no beds field are studios (Bayut omits "Studio" on some cards)
    if beds is None and get_aria("Type") == "Apartment":
        beds = 0

    baths_text = get_aria("Baths")
    baths = int(re.search(r"(\d+)", baths_text).group(1)) if baths_text and re.search(r"(\d+)", baths_text) else None

    area_text = get_aria("Area")
    size = None
    if area_text:
        m = re.search(r"([\d,]+)", area_text)
        if m:
            size = int(m.group(1).replace(",", ""))

    location_text = get_aria("Location") or ""
    loc_parts = [p.strip() for p in location_text.split(",") if p.strip()]

    tower = sub_community = community = city = None
    if len(loc_parts) == 5:
        # tower, sub, community, parent, city — use community (index 2)
        tower, sub_community, community, city = loc_parts[0], loc_parts[1], loc_parts[2], loc_parts[4]
    elif len(loc_parts) >= 6:
        # deep nesting — community is index -3, sub is -4
        tower = loc_parts[0]
        sub_community = loc_parts[-4]
        community = loc_parts[-3]
        city = loc_parts[-1]
    elif len(loc_parts) == 4:
        tower, sub_community, community, city = loc_parts[0], loc_parts[1], loc_parts[2], loc_parts[3]
    elif len(loc_parts) == 3:
        sub_community, community, city = loc_parts[0], loc_parts[1], loc_parts[2]
    elif len(loc_parts) == 2:
        community, city = loc_parts[0], loc_parts[1]
    elif len(loc_parts) == 1:
        community = loc_parts[0]

    # Known community overrides — some 5-part locations need the parent
    COMMUNITY_OVERRIDES = {
        'Kingdom of Sheba': 'Palm Jumeirah',
        'Old Town': 'Downtown Dubai',
        'Opera District': 'Downtown Dubai',
        'Golf Town': 'DAMAC Hills',
        'JVC District 10': 'Jumeirah Village Circle (JVC)',
        'JVC District 11': 'Jumeirah Village Circle (JVC)',
        'JVC District 12': 'Jumeirah Village Circle (JVC)',
        'JVC District 13': 'Jumeirah Village Circle (JVC)',
        'JVC District 14': 'Jumeirah Village Circle (JVC)',
        'JVC District 15': 'Jumeirah Village Circle (JVC)',
        'JVC District 16': 'Jumeirah Village Circle (JVC)',
        'JVC District 18': 'Jumeirah Village Circle (JVC)',
    }
    if community in COMMUNITY_OVERRIDES:
        # For JVC Districts: community becomes JVC, sub_community becomes the district
        # tower stays as is (the actual building name)
        if not tower:
            tower = sub_community
        sub_community = community
        community = COMMUNITY_OVERRIDES[community]

    # Listing URL
    link_el = card.find("a", href=re.compile(r"/property/"))
    listing_url = link_el["href"] if link_el else None
    listing_id = None
    if listing_url:
        id_match = re.search(r"details-(\d+)", listing_url)
        listing_id = id_match.group(1) if id_match else None

    # Agent name
    agent_el = card.find(attrs={"aria-label": "Agent logo"})
    agent_name = agent_el.get("title", "").strip() if agent_el else None

    # Listed date → days on market
    card_text = card.get_text()
    listed_date = None
    dom = None
    date_match = re.search(r"on (\d+)\w* of (\w+) (\d{4})", card_text)
    if date_match:
        try:
            from datetime import datetime
            day, month_name, year = date_match.group(1), date_match.group(2), date_match.group(3)
            listed_date = datetime.strptime(f"{day} {month_name} {year}", "%d %B %Y").strftime("%Y-%m-%d")
            dom = (datetime.utcnow() - datetime.strptime(listed_date, "%Y-%m-%d")).days
        except (ValueError, Exception):
            pass

    # Promotional status — check both text content AND aria-labels (badges are often images)
    promo = None
    card_html = str(card)
    if card.find(attrs={"aria-label": "Signature"}) or "Signature" in card_text:
        promo = "Signature"
    elif card.find(attrs={"aria-label": "Hot"}) or "Hot" in card_text:
        promo = "Hot"

    # TruBroker verification (agent badge, not spend)
    trubroker = "TruBroker" in card_text

    # Price per sqft
    psqft = None
    if price_num and size and size > 0:
        psqft = round(price_num / size)

    return {
        "listing_id": listing_id,
        "url": listing_url,
        "price": f"AED {price_text}",
        "price_num": price_num,
        "price_sqft": psqft,
        "purpose": purpose,
        "frequency": frequency.lower() if frequency else None,
        "type": get_aria("Type"),
        "bedrooms": beds,
        "bathrooms": baths,
        "size_sqft": size,
        "title": get_aria("Title"),
        "location": location_text,
        "tower": tower,
        "sub_community": sub_community,
        "community": community,
        "city": city,
        "agent": agent_name,
        "listed_date": listed_date,
        "dom": dom,
        "promo": promo,
        "verified": bool(card.find(attrs={"aria-label": "TruBroker"})) or trubroker,
        "trubroker": trubroker,
        "off_plan": "Off-Plan" in card_text,
    }


def parse_page_listings(html: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    listings = []
    for card in soup.find_all(attrs={"aria-label": "Listing"}):
        l = parse_listing_card(card)
        if l:
            listings.append(l)
    return listings


def get_total_listings(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.string if soup.title else ""
    m = re.search(r"(\d+)\s*Properties", title)
    return int(m.group(1)) if m else 0


def _dedup_listings(listings):
    """Deduplicate listings by listing_id, keeping first occurrence."""
    seen = set()
    result = []
    for l in listings:
        lid = l.get('listing_id')
        if lid and lid in seen:
            continue
        if lid:
            seen.add(lid)
        result.append(l)
    return result


def scrape_all_listings(concurrency: int = 3) -> dict:
    """Scrape all Huspy listings with multi-pass to handle pagination instability.
    
    Bayut's pagination shifts between requests, causing overlap and missed listings.
    Lower concurrency reduces churn. A second pass fills remaining gaps.
    """
    print(f"⬡ Huspy Tracker — Full scrape (concurrency={concurrency})")
    start = time.time()

    # First page to get total count
    _, html1 = scrape_page(1)
    total_expected = get_total_listings(html1)
    page1_listings = parse_page_listings(html1)
    total_pages = (total_expected + 23) // 24  # ceiling division

    print(f"  {total_expected} listings, {total_pages} pages")
    print(f"  Page 1: {len(page1_listings)} listings")

    all_listings = list(page1_listings)
    credits_used = 75

    # Pass 1: scrape all pages
    remaining_pages = list(range(2, total_pages + 1))

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(scrape_page, p): p for p in remaining_pages}
        completed = 0

        for future in as_completed(futures):
            page_num, html = future.result()
            completed += 1
            credits_used += 75

            if html:
                listings = parse_page_listings(html)
                all_listings.extend(listings)
                if completed % 10 == 0 or completed == len(remaining_pages):
                    print(f"  Progress: {completed}/{len(remaining_pages)} pages ({len(all_listings)} listings)")
            else:
                print(f"  Page {page_num}: failed")

    all_listings = _dedup_listings(all_listings)
    unique_pass1 = len(all_listings)
    gap = total_expected - unique_pass1
    print(f"  Pass 1: {unique_pass1} unique / {total_expected} expected ({gap} gap)")

    # Pass 2: if significant gap, re-scrape to fill it
    if gap > total_expected * 0.05:  # >5% gap
        print(f"  Pass 2: re-scraping {total_pages} pages to fill {gap} gap...")
        pass2_pages = list(range(1, total_pages + 1))
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(scrape_page, p): p for p in pass2_pages}
            completed = 0
            for future in as_completed(futures):
                page_num, html = future.result()
                completed += 1
                credits_used += 75
                if html:
                    listings = parse_page_listings(html)
                    all_listings.extend(listings)
                if completed % 20 == 0:
                    print(f"    Pass 2 progress: {completed}/{len(pass2_pages)}")
        all_listings = _dedup_listings(all_listings)
        print(f"  Pass 2: {len(all_listings)} unique ({len(all_listings) - unique_pass1} new)")

    print(f"  Coverage: {len(all_listings)}/{total_expected} ({len(all_listings)/total_expected*100:.1f}%)" if total_expected else "")

    elapsed = time.time() - start
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "total_expected": total_expected,
        "total_scraped": len(all_listings),
        "pages_scraped": total_pages,
        "credits_used": credits_used,
        "elapsed_seconds": round(elapsed),
        "listings": all_listings,
    }

    print(f"\n  ✓ {len(all_listings)} listings | {total_pages} pages | {credits_used} credits | {elapsed:.0f}s")
    return result


def save_snapshot(result: dict, data_dir: str = "data") -> str:
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, f"{result['date']}.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    return path


if __name__ == "__main__":
    result = scrape_all_listings()
    path = save_snapshot(result)
    print(f"  Saved to {path}")
