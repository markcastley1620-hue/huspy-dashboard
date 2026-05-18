---
summary: "Nexus local tool notes"
---

# TOOLS.md - Local Notes

## Bayut Brochure Generator

**Location:** `bayut-brochure/`
**Purpose:** Scrape Bayut property listings → remove watermarks → generate PDF brochure

### How to run
```bash
cd /data/.openclaw/workspace/bayut-brochure
python3 main.py "<bayut_url>"
```

### How it works
1. **Scraper** (`scraper.py`) — Uses ScrapingBee stealth proxy (75 credits/call) to bypass Bayut's bot protection. Extracts data from ARIA labels in HTML.
2. **Watermark removal** (`watermark.py`) — Downloads images with Referer header, uses OpenCV inpainting to detect/remove watermarks.
3. **Brochure** (`brochure.py`) — Generates PDF with ReportLab: hero image, property details grid, description, photo gallery.

### When someone sends a Bayut link
1. Run the pipeline via `python3 main.py <url>`
2. Send back the generated PDF from `bayut-brochure/output/`
3. Each run costs ~75 ScrapingBee credits

### Config
- ScrapingBee API key in `bayut-brochure/.env`
- Branding: pass `branding` dict to `generate()` with `agent_name`, `company`, `phone`, `email`
- Images: keeps original Bayut resolution (800x600 / 400x300), max 10 per brochure

### Known issues
- Bayut image CDN requires `Referer: https://www.bayut.com/` header
- ScrapingBee stealth proxy is required (regular/premium proxy still gets CAPTCHA'd)
- 1600x1200 image resolution URLs return 403 — use original sizes only
- Watermark removal is best-effort (OpenCV inpainting, not perfect for heavy overlays)
