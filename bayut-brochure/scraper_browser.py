"""
Browser-based Bayut scraper.
Called by Rook via OpenClaw browser tool — this module parses the extracted page data.
Does NOT drive the browser itself (that's done by the agent).
"""

import json
import re


def parse_snapshot_text(snapshot_text: str) -> dict:
    """Parse property data from a browser snapshot text dump."""
    data = {
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
        "description": None,
        "amenities": [],
        "images": [],
    }
    # This is a placeholder — actual parsing happens in the agent layer
    # via browser snapshot + JS evaluation
    return data


def parse_property_json(raw: str) -> dict:
    """Parse property data from JSON extracted via browser JS evaluation."""
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {}

    data = {
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
        "description": None,
        "amenities": [],
        "images": [],
    }

    # Handle various data shapes from Bayut's Next.js data
    if isinstance(obj, dict):
        _extract_from_dict(obj, data)

    return data


def _extract_from_dict(obj: dict, data: dict, depth=0):
    """Recursively extract property fields from nested dict."""
    if depth > 10:
        return

    # Direct field extraction
    for key, val in obj.items():
        if val is None:
            continue

        key_lower = key.lower()

        # Title
        if key_lower in ("title", "name") and isinstance(val, str) and len(val) > 10 and not data["title"]:
            data["title"] = val

        # Price
        if key_lower == "price" and not data["price"]:
            if isinstance(val, (int, float)):
                data["price"] = f"AED {val:,.0f}"
            elif isinstance(val, str):
                data["price"] = val

        # Bedrooms
        if key_lower in ("beds", "bedrooms", "numberofbedrooms", "rooms") and not data["bedrooms"]:
            data["bedrooms"] = val

        # Bathrooms
        if key_lower in ("baths", "bathrooms") and not data["bathrooms"]:
            data["bathrooms"] = val

        # Area/Size
        if key_lower in ("area", "size", "builtuparea") and not data["size"]:
            if isinstance(val, (int, float)):
                data["size"] = f"{val:,.0f} sqft"
            elif isinstance(val, dict):
                v = val.get("value") or val.get("size")
                u = val.get("unit", "sqft")
                if v:
                    data["size"] = f"{v} {u}"

        # Type
        if key_lower in ("type", "category", "propertytype", "categorytype") and isinstance(val, str) and not data["type"]:
            data["type"] = val

        # Purpose
        if key_lower in ("purpose",) and isinstance(val, str) and not data["purpose"]:
            data["purpose"] = val

        # Furnishing
        if key_lower in ("furnishingstatus", "furnishing") and isinstance(val, str) and not data["furnishing"]:
            data["furnishing"] = val

        # Reference
        if key_lower in ("referencenumber", "reference", "externalid", "id") and not data["reference"]:
            if isinstance(val, (str, int)):
                data["reference"] = str(val)

        # Description
        if key_lower == "description" and isinstance(val, str) and len(val) > 20 and not data["description"]:
            data["description"] = val

        # Location
        if key_lower == "location" and not data["location"]:
            if isinstance(val, str):
                data["location"] = val
            elif isinstance(val, list) and val:
                names = []
                for loc in val:
                    if isinstance(loc, dict):
                        n = loc.get("name") or loc.get("name_l1") or ""
                        if n:
                            names.append(n)
                if names:
                    data["location"] = ", ".join(names)
            elif isinstance(val, dict):
                n = val.get("name") or val.get("full") or val.get("name_l1") or ""
                if n:
                    data["location"] = n

        # Photos
        if key_lower in ("photos", "images", "photoids") and isinstance(val, list) and not data["images"]:
            for item in val:
                if isinstance(item, dict):
                    url = item.get("url") or item.get("main") or item.get("fullUrl") or ""
                    if not url and "id" in item:
                        url = item["id"]  # Sometimes just IDs
                    if url and isinstance(url, str):
                        data["images"].append(url)
                elif isinstance(item, str):
                    data["images"].append(item)

        # Cover photo
        if key_lower == "coverphoto" and isinstance(val, dict) and not data["images"]:
            url = val.get("url") or val.get("main") or ""
            if url:
                data["images"].insert(0, url)

        # Amenities
        if key_lower in ("amenities",) and isinstance(val, list) and not data["amenities"]:
            for a in val:
                if isinstance(a, str):
                    data["amenities"].append(a)
                elif isinstance(a, dict):
                    text = a.get("text") or a.get("name") or a.get("externalGroupID") or ""
                    if text:
                        data["amenities"].append(text)

        # Recurse into nested dicts
        if isinstance(val, dict):
            _extract_from_dict(val, data, depth + 1)
