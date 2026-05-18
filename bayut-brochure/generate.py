#!/usr/bin/env python3
"""
Generate brochure from pre-extracted JSON data.
Called by Rook after browser extraction.

Usage: python3 generate.py <json_file> [output_path]
  json_file: path to JSON with property data (must include 'images' array of URLs)
"""

import os
import sys
import json
import time
from watermark import process_images
from brochure import generate_brochure


def generate_from_json(json_path: str, output_path: str | None = None, branding: dict | None = None) -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    timestamp = int(time.time())
    tmp_dir = os.path.join(base_dir, "tmp", f"job_{timestamp}")
    img_dir = os.path.join(tmp_dir, "images")
    output_dir = os.path.join(base_dir, "output")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    with open(json_path) as f:
        data = json.load(f)

    print(f"♜ Bayut Brochure Generator")
    print(f"  Title: {data.get('title', 'N/A')}")
    print(f"  Price: {data.get('price', 'N/A')}")
    print(f"  Images: {len(data.get('images', []))}")
    print()

    # Process images
    images = data.get("images", [])[:10]
    processed_paths = []
    if images:
        print(f"Processing {len(images)} images...")
        processed_paths = process_images(images, img_dir)
        print(f"  Done: {len(processed_paths)} images")
    print()

    # Generate PDF
    if not output_path:
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in (data.get("title") or "property"))
        safe_title = safe_title.strip()[:60] or "property"
        output_path = os.path.join(output_dir, f"{safe_title}_{timestamp}.pdf")

    print("Generating PDF...")
    generate_brochure(data, processed_paths, output_path, branding)
    print(f"  ✓ {output_path}")

    # Cleanup
    import shutil
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    return {"output_path": output_path, "images_processed": len(processed_paths)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate.py <json_file> [output_path]")
        sys.exit(1)
    result = generate_from_json(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps(result, indent=2))
