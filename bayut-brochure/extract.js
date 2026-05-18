// JS to evaluate in browser on a Bayut property page to extract all data
(() => {
  const result = {
    title: null,
    price: null,
    location: null,
    bedrooms: null,
    bathrooms: null,
    size: null,
    type: null,
    purpose: null,
    furnishing: null,
    reference: null,
    description: null,
    amenities: [],
    images: [],
  };

  // Method 1: __NEXT_DATA__
  const nextDataEl = document.getElementById('__NEXT_DATA__');
  if (nextDataEl) {
    try {
      const nd = JSON.parse(nextDataEl.textContent);
      const props = nd?.props?.pageProps || {};
      
      // Find the property object
      let prop = null;
      for (const key of Object.keys(props)) {
        const val = props[key];
        if (val && typeof val === 'object' && ('price' in val || 'title' in val || 'beds' in val)) {
          prop = val;
          break;
        }
      }
      
      if (prop) {
        result.title = prop.title || prop.name;
        result.bedrooms = prop.beds || prop.bedrooms || prop.rooms;
        result.bathrooms = prop.baths || prop.bathrooms;
        result.type = prop.type || prop.category;
        result.purpose = prop.purpose;
        result.furnishing = prop.furnishingStatus || prop.furnishing;
        result.reference = prop.referenceNumber || prop.reference || prop.externalID;
        result.description = prop.description;
        
        // Price
        if (prop.price) {
          const currency = prop.currency || 'AED';
          result.price = typeof prop.price === 'number' 
            ? `${currency} ${prop.price.toLocaleString()}` 
            : `${currency} ${prop.price}`;
        }
        
        // Size
        if (prop.area) {
          result.size = typeof prop.area === 'number' 
            ? `${prop.area.toLocaleString()} sqft`
            : `${prop.area}`;
        }
        
        // Location
        if (prop.location) {
          if (Array.isArray(prop.location)) {
            result.location = prop.location.map(l => l.name || l.name_l1 || '').filter(Boolean).join(', ');
          } else if (typeof prop.location === 'string') {
            result.location = prop.location;
          }
        }
        
        // Images
        if (prop.photos && Array.isArray(prop.photos)) {
          result.images = prop.photos.map(p => p.url || p.main || p).filter(Boolean).slice(0, 10);
        } else if (prop.coverPhoto) {
          result.images = [prop.coverPhoto.url || prop.coverPhoto.main].filter(Boolean);
        }
        
        // Amenities
        if (prop.amenities && Array.isArray(prop.amenities)) {
          result.amenities = prop.amenities.map(a => a.text || a.name || a.externalGroupID || String(a)).filter(Boolean);
        }
      }
    } catch(e) { /* ignore parse errors */ }
  }

  // Method 2: DOM fallback
  if (!result.title) {
    const h1 = document.querySelector('h1');
    if (h1) result.title = h1.textContent.trim();
  }

  if (!result.price) {
    // Look for price element - Bayut uses aria-label="Price" or specific class patterns
    const priceEl = document.querySelector('[aria-label="Price"], [class*="price" i], [data-testid*="price" i]');
    if (priceEl) result.price = priceEl.textContent.trim();
  }

  if (!result.images.length) {
    // Get images from gallery
    const imgs = document.querySelectorAll('img[src*="bayut"], img[src*="imagecdn"]');
    const seen = new Set();
    imgs.forEach(img => {
      const src = img.src || img.dataset.src || '';
      if (src && !src.includes('logo') && !src.includes('avatar') && !src.includes('icon') && !seen.has(src)) {
        seen.add(src);
        result.images.push(src);
      }
    });
    result.images = result.images.slice(0, 10);
  }

  // Method 3: JSON-LD
  document.querySelectorAll('script[type="application/ld+json"]').forEach(el => {
    try {
      const ld = JSON.parse(el.textContent);
      const items = Array.isArray(ld) ? ld : [ld];
      items.forEach(item => {
        if (item['@type'] && ['SingleFamilyResidence','Apartment','House','RealEstateListing','Product'].includes(item['@type'])) {
          result.title = result.title || item.name;
          result.description = result.description || item.description;
          if (item.offers?.price && !result.price) {
            result.price = `${item.offers.priceCurrency || 'AED'} ${Number(item.offers.price).toLocaleString()}`;
          }
          if (item.image && !result.images.length) {
            result.images = (Array.isArray(item.image) ? item.image : [item.image])
              .map(i => typeof i === 'string' ? i : i.url || i.contentUrl || '')
              .filter(Boolean)
              .slice(0, 10);
          }
        }
      });
    } catch(e) {}
  });

  return JSON.stringify(result);
})()
