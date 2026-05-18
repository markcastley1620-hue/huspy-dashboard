"""
Bayut property listing scraper using ScrapingBee stealth proxy.
Extracts property details from ARIA labels and HTML structure.
"""

import os
import re
import json
import requests
from bs4 import BeautifulSoup

SCRAPINGBEE_KEY = os.environ.get(
    "SCRAPINGBEE_API_KEY",
    "QNG91WITJC8K7U39RMHTB7CAVQOUGTK8C09PPFJESMCYT2MNGJY19FLUQWDK3NABEC4PWPVF5HWI2CR0"
)


def scrape_bayut(url: str) -> dict:
    """Scrape a Bayut listing page via ScrapingBee and return structured data."""

    # Fetch via ScrapingBee stealth proxy (with retry)
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get("https://app.scrapingbee.com/api/v1/", params={
                "api_key": SCRAPINGBEE_KEY,
                "url": url,
                "stealth_proxy": "true",
                "country_code": "ae",
            }, timeout=120)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            last_err = e
            if attempt < 2:
                import time
                print(f"  Retry {attempt + 1}/2 after error: {e}")
                time.sleep(5)
            else:
                raise last_err

    credits_used = resp.headers.get("Spb-cost", "?")
    print(f"  ScrapingBee credits used: {credits_used}")

    soup = BeautifulSoup(resp.text, "lxml")

    data = {
        "url": url,
        "title": None,
        "price": None,
        "location": None,
        "bedrooms": None,
        "bathrooms": None,
        "size": None,
        "type": None,
        "purpose": None,
        "furnishing": None,
        "reference": None,
        "completion": None,
        "description": None,
        "amenities": [],
        "images": [],
        "agent_name": None,
        "agent_company": None,
        "permit_number": None,
    }

    # === Extract from ARIA labels (most reliable on Bayut) ===
    aria_map = {}
    for el in soup.find_all(attrs={"aria-label": True}):
        label = el.get("aria-label", "").lower().strip()
        text = el.get_text(strip=True)
        aria_map[label] = text

    # Title from H1 or property overview
    h1 = soup.find("h1")
    if h1:
        data["title"] = h1.get_text(strip=True)

    # Price
    price_el = soup.find(attrs={"aria-label": "Price"})
    if price_el:
        price_text = price_el.get_text(strip=True)
        # Clean price
        price_text = re.sub(r'[^\d,.]', '', price_text)
        data["price"] = f"AED {price_text}"
    if not data["price"]:
        # Fallback: look in property basic info
        basic = aria_map.get("property basic info", "")
        m = re.search(r'AED[\s]*([\d,]+)', basic)
        if m:
            data["price"] = f"AED {m.group(1)}"

    # Location from property header
    header_el = soup.find(attrs={"aria-label": "Property header"})
    if header_el:
        data["location"] = header_el.get_text(strip=True)
    if not data["location"]:
        # Try breadcrumb
        bc = aria_map.get("breadcrumb", "")
        if bc:
            parts = bc.split("Bayut")[0].strip()
            data["location"] = parts.rstrip(" -,")

    # Beds, Baths, Area
    beds_el = soup.find(attrs={"aria-label": "Beds"})
    if beds_el:
        m = re.search(r'(\d+)', beds_el.get_text())
        if m:
            data["bedrooms"] = m.group(1)

    baths_el = soup.find(attrs={"aria-label": "Baths"})
    if baths_el:
        m = re.search(r'(\d+)', baths_el.get_text())
        if m:
            data["bathrooms"] = m.group(1)

    area_el = soup.find(attrs={"aria-label": "Area"})
    if area_el:
        data["size"] = area_el.get_text(strip=True)

    # Property details section
    details_el = soup.find(attrs={"aria-label": "Property details"})
    if details_el:
        details_text = details_el.get_text(" ", strip=True)

        # Type
        type_el = soup.find(attrs={"aria-label": "Type"})
        if type_el:
            data["type"] = type_el.get_text(strip=True)

        # Purpose
        purpose_el = soup.find(attrs={"aria-label": "Purpose"})
        if purpose_el:
            data["purpose"] = purpose_el.get_text(strip=True)

        # Reference (strip Bayut prefix)
        ref_el = soup.find(attrs={"aria-label": "Reference"})
        if ref_el:
            ref_text = ref_el.get_text(strip=True)
            ref_text = re.sub(r'^Bayut\s*[-–—]\s*', '', ref_text)
            data["reference"] = ref_text

        # Completion
        completion_el = soup.find(attrs={"aria-label": "Completion status"})
        if completion_el:
            data["completion"] = completion_el.get_text(strip=True)

        # Furnishing
        furn_el = soup.find(attrs={"aria-label": re.compile(r"[Ff]urnish", re.I)})
        if furn_el:
            data["furnishing"] = furn_el.get_text(strip=True)

    # Description
    desc_el = soup.find(attrs={"aria-label": re.compile(r"description", re.I)})
    if desc_el:
        data["description"] = desc_el.get_text(" ", strip=True)
        # Clean up "Read More" suffix
        data["description"] = re.sub(r'\s*Read More\s*$', '', data["description"])

    # Amenities
    amenities_el = soup.find(attrs={"aria-label": re.compile(r"amenities|features", re.I)})
    if amenities_el:
        for span in amenities_el.find_all("span"):
            text = span.get_text(strip=True)
            if text and len(text) > 1 and text not in ("Amenities", "Features"):
                data["amenities"].append(text)

    # Permit number
    permit_el = soup.find(attrs={"aria-label": re.compile(r"permit", re.I)})
    if permit_el:
        data["permit_number"] = permit_el.get_text(strip=True)

    # Images - prefer gallery photo grid (correct order, 800x600)
    seen = set()
    gallery_el = (
        soup.find(attrs={"aria-label": "Gallery dialog photo grid"})
        or soup.find(attrs={"aria-label": re.compile(r"gallery.*photo", re.I)})
        or soup.find(attrs={"aria-label": re.compile(r"gallery.*dialog", re.I)})
    )
    img_source = gallery_el if gallery_el else soup
    for img in img_source.find_all("img"):
        src = img.get("src", "")
        if "bayut.com" in src and all(skip not in src for skip in ("logo", "icon", "avatar", "static", "apple-touch")):
            base = re.sub(r'-\d+x\d+\.', '-', src.split("?")[0])  # normalise for dedup
            if base not in seen:
                seen.add(base)
                data["images"].append(src)

    data["images"] = data["images"][:10]

    # Agent info
    agent_el = soup.find(attrs={"aria-label": re.compile(r"agent", re.I)})
    if agent_el:
        text = agent_el.get_text(" ", strip=True)
        # Often format: "Agent: Name" or just the name
        name_match = re.search(r'Agent[:\s]*(.+)', text)
        if name_match:
            data["agent_name"] = name_match.group(1).strip()

    company_el = soup.find(attrs={"aria-label": re.compile(r"listing by|agency", re.I)})
    if company_el:
        text = company_el.get_text(strip=True)
        text = re.sub(r'^Listing by\s*', '', text)
        data["agent_company"] = text

    return data


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = scrape_bayut(sys.argv[1])
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Usage: python3 scraper.py <bayut_url>")
