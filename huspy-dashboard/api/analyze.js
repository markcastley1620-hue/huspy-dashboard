// Spend Advisor API — analyzes a Bayut listing URL
// Called from the dashboard, proxied through a Supabase Edge Function or direct

const SCRAPINGBEE_KEY = 'QNG91WITJC8K7U39RMHTB7CAVQOUGTK8C09PPFJESMCYT2MNGJY19FLUQWDK3NABEC4PWPVF5HWI2CR0';

async function analyzeListing(bayutUrl) {
  // 1. Scrape the listing page
  const resp = await fetch(`https://app.scrapingbee.com/api/v1/?api_key=${SCRAPINGBEE_KEY}&url=${encodeURIComponent(bayutUrl)}&stealth_proxy=true&country_code=ae`);
  const html = await resp.text();
  
  // 2. Parse listing data (server-side would use cheerio, but for edge function use regex)
  const data = parseListingHtml(html);
  return data;
}

function parseListingHtml(html) {
  const get = (label) => {
    const m = html.match(new RegExp(`aria-label="${label}"[^>]*>([^<]*)<`, 'i'));
    return m ? m[1].trim() : null;
  };
  
  const getAfterLabel = (label) => {
    const m = html.match(new RegExp(`aria-label="${label}"[^>]*>[\\s\\S]*?<[^>]*>([^<]+)`, 'i'));
    return m ? m[1].trim() : null;
  };

  return {
    price: parseInt((get('Price') || '0').replace(/,/g, '')),
    beds: parseInt((get('Beds') || '0').replace(/[^0-9]/g, '')) || 0,
    baths: parseInt((get('Baths') || '0').replace(/[^0-9]/g, '')) || 0,
    sqft: parseInt((get('Area') || '0').replace(/[^0-9]/g, '')) || 0,
    type: get('Type'),
    location: get('Property header'),
    agent: get('Agent name'),
    buildingName: get('Building Name'),
    developer: get('Developer'),
    builtUpArea: get('Built-up Area'),
    yearOfCompletion: get('Year of Completion'),
    furnishing: get('Furnishing'),
    serviceCharges: get('Service charges'),
  };
}

module.exports = { analyzeListing };
