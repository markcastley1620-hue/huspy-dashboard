#!/usr/bin/env python3
"""
Bayut Property Brochure Generator
Usage: python3 main.py <bayut_url> [output_path]
"""

import os
import sys
import json
import time
import shutil
from scraper import scrape_bayut
from watermark import process_images
from brochure import generate_brochure


def generate(url: str, output_path: str | None = None, branding: dict | None = None) -> dict:
    """
    Full pipeline: scrape → download/clean images → generate PDF.
    Returns dict with output_path and property_data.
    """
    timestamp = int(time.time())
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tmp_dir = os.path.join(base_dir, "tmp", f"job_{timestamp}")
    img_dir = os.path.join(tmp_dir, "images")
    output_dir = os.path.join(base_dir, "output")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    print(f"♜ Bayut Brochure Generator")
    print(f"  URL: {url}")
    print()

    # Step 1: Scrape
    print("1/3 Scraping property data...")
    data = scrape_bayut(url)

    print(f"  Title: {data.get('title', 'N/A')}")
    print(f"  Price: {data.get('price', 'N/A')}")
    print(f"  Location: {data.get('location', 'N/A')}")
    print(f"  Beds: {data.get('bedrooms', 'N/A')} | Baths: {data.get('bathrooms', 'N/A')} | Size: {data.get('size', 'N/A')}")
    print(f"  Images found: {len(data.get('images', []))}")
    print()

    # Step 2: Download and clean images
    images = data.get("images", [])
    processed_paths = []
    if images:
        print(f"2/3 Processing {len(images)} images (download + watermark removal)...")
        processed_paths = process_images(images, img_dir)
        print(f"  Processed: {len(processed_paths)} images")
    else:
        print("2/3 No images found, skipping.")
    print()

    # Step 3: Generate PDF
    if not output_path:
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in (data.get("title") or "property"))
        safe_title = safe_title.strip()[:60] or "property"
        output_path = os.path.join(output_dir, f"{safe_title}_{timestamp}.pdf")

    print("3/3 Generating PDF brochure...")
    generate_brochure(data, processed_paths, output_path, branding)
    print(f"  ✓ Saved: {output_path}")

    # Cleanup tmp images
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    return {
        "output_path": output_path,
        "property_data": data,
        "images_processed": len(processed_paths),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 main.py <bayut_url> [output_path]")
        sys.exit(1)

    url = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else None

    result = generate(url, output)
    print()
    print(json.dumps({
        "output": result["output_path"],
        "title": result["property_data"].get("title"),
        "price": result["property_data"].get("price"),
        "images": result["images_processed"],
    }, indent=2))
