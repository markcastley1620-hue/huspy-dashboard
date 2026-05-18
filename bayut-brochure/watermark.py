"""
Watermark removal for Bayut property images.
Uses LaMa inpainting with a center-band mask targeting the watermark zone.
The mask is kept tight (~12% of image) so LaMa produces clean results.
"""

import cv2
import numpy as np
from PIL import Image as PILImage
import requests
import os

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.bayut.com/",
}

_lama = None

def _get_lama():
    global _lama
    if _lama is None:
        from simple_lama_inpainting import SimpleLama
        _lama = SimpleLama()
    return _lama


def download_image(url: str) -> np.ndarray | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        arr = np.frombuffer(resp.content, np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return None


def make_watermark_mask(img: np.ndarray) -> np.ndarray:
    """
    Create a mask targeting the watermark zone.
    
    Bayut agency watermarks are consistently placed in the center of the image.
    Strategy: use brightness/saturation anomaly detection ONLY within the center
    band, with generous coverage to catch the full text.
    """
    h, w = img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    # Center region where watermark text sits
    # Typically ~30% width × ~15% height in the middle
    y1, y2 = int(h * 0.33), int(h * 0.62)
    x1, x2 = int(w * 0.22), int(w * 0.78)

    # Within this region, detect bright/desaturated pixels (the white overlay)
    roi = img[y1:y2, x1:x2]
    roi_lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    L = roi_lab[:, :, 0].astype(np.float64)
    S = roi_hsv[:, :, 1].astype(np.float64)

    ksize = 25
    L_med = cv2.medianBlur(roi_lab[:, :, 0], ksize).astype(np.float64)
    S_med = cv2.medianBlur(roi_hsv[:, :, 1], ksize).astype(np.float64)

    lift = L - L_med
    sdrop = S_med - S

    # Detect watermark pixels: brighter AND less saturated than surroundings
    wm_pixels = ((lift > 8) & (sdrop > 5)).astype(np.uint8) * 255

    # Morphological: connect text strokes, fill gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    wm_pixels = cv2.morphologyEx(wm_pixels, cv2.MORPH_CLOSE, kernel)
    wm_pixels = cv2.dilate(wm_pixels, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=3)

    # Remove small noise (keep only substantial regions)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(wm_pixels)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] < 500:
            wm_pixels[labels == i] = 0

    # Place back into full mask
    mask[y1:y2, x1:x2] = wm_pixels

    return mask


def remove_watermark(img: np.ndarray) -> np.ndarray:
    """Remove watermark using LaMa with targeted mask."""
    mask = make_watermark_mask(img)

    if cv2.countNonZero(mask) < 500:
        return img  # No significant watermark detected

    coverage = cv2.countNonZero(mask) / mask.size * 100
    if coverage > 25:
        # Mask too large — would damage image. Skip.
        return img

    lama = _get_lama()
    img_pil = PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    mask_pil = PILImage.fromarray(mask)
    result_pil = lama(img_pil, mask_pil)
    return cv2.cvtColor(np.array(result_pil), cv2.COLOR_RGB2BGR)


def process_image(url: str, output_path: str) -> bool:
    img = download_image(url)
    if img is None:
        return False
    cleaned = remove_watermark(img)
    cv2.imwrite(output_path, cleaned, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return True


def process_images(urls: list, output_dir: str) -> list:
    os.makedirs(output_dir, exist_ok=True)
    results = []
    for i, url in enumerate(urls):
        out = os.path.join(output_dir, f"image_{i+1:02d}.jpg")
        if process_image(url, out):
            results.append(out)
            print(f"  ✓ Image {i+1}/{len(urls)}")
        else:
            print(f"  ✗ Image {i+1}/{len(urls)} failed")
    return results
