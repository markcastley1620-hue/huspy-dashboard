#!/usr/bin/env node
// Build dashboard from Salesforce XML feed data
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'huspy-tracker', 'data');
const TEMPLATE = path.join(__dirname, 'public', 'index.html');
const OUT_DIR = path.join(__dirname, 'dist');

function priceBand(price, purpose) {
  if (!price) return 'Unknown';
  if (purpose === 'rent') {
    if (price < 50000) return 'Under 50K';
    if (price < 100000) return '50K–100K';
    if (price < 200000) return '100K–200K';
    if (price < 350000) return '200K–350K';
    return '350K+';
  }
  if (price < 1000000) return 'Under 1M';
  if (price < 2000000) return '1M–2M';
  if (price < 5000000) return '2M–5M';
  if (price < 10000000) return '5M–10M';
  return '10M+';
}

function formatPrice(price, purpose) {
  if (!price) return '—';
  return 'AED ' + price.toLocaleString('en-US');
}

// Load current XML feed
const feedPath = path.join(DATA_DIR, 'xml_feed.json');
if (!fs.existsSync(feedPath)) { console.error('No xml_feed.json'); process.exit(1); }
const feed = JSON.parse(fs.readFileSync(feedPath, 'utf8'));

// Load previous snapshot for "new" detection
const snapFiles = fs.readdirSync(DATA_DIR)
  .filter(f => /^xml_\d{4}-\d{2}-\d{2}\.json$/.test(f)).sort();
let prevRefs = new Set();
if (snapFiles.length > 0) {
  const prev = JSON.parse(fs.readFileSync(path.join(DATA_DIR, snapFiles[snapFiles.length - 1]), 'utf8'));
  prevRefs = new Set(prev.listings.map(l => l.ref));
}

const listings = feed.listings;
const newListings = prevRefs.size > 0 
  ? listings.filter(l => !prevRefs.has(l.ref))
  : [];
const removedCount = prevRefs.size > 0
  ? [...prevRefs].filter(r => !new Set(listings.map(l => l.ref)).has(r)).length
  : 0;

const mapped = listings.map(l => ({
  id: l.ref || l.sf_id,
  community: l.community,
  sub_community: l.sub_community,
  tower: l.tower,
  type: l.type,
  bedrooms: l.bedrooms,
  price: l.price,
  priceFormatted: formatPrice(l.price, l.purpose),
  purpose: l.purpose,
  agent: l.agent,
  agentEmail: l.agent_email,
  agentLevel: l.promo === 'Signature' ? 'Signature' : l.promo === 'Hot' ? 'Hot' : l.trubroker ? 'TruBroker' : l.verified ? 'Verified' : 'Standard',
  spend: l.promo || null,
  trubroker: l.trubroker || false,
  priceBand: priceBand(l.price, l.purpose),
  isNew: prevRefs.size > 0 ? !prevRefs.has(l.ref) : false,
  offPlan: l.off_plan,
  size: l.size_sqft,
  furnished: l.furnished,
  permit: l.permit,
  url: l.bayut_url || null,
  listedDate: l.listed_date || null,
}));

const data = {
  latestDate: feed.date || new Date().toISOString().slice(0, 10),
  prevDate: snapFiles.length > 0 ? snapFiles[snapFiles.length - 1].replace('xml_', '').replace('.json', '') : null,
  source: 'Salesforce XML',
  total: listings.length,
  sale: listings.filter(l => l.purpose === 'sale').length,
  rent: listings.filter(l => l.purpose === 'rent').length,
  newCount: newListings.length,
  removedCount,
  allListings: mapped,
  newListings: mapped.filter(l => l.isNew),
  agentRegistry: [], // No longer needed, we have 100% coverage
};

// Build HTML
let html = fs.readFileSync(TEMPLATE, 'utf8');
html = html.replace(
  /async load\(\) \{[\s\S]*?this\.loading = false;\s*\}/,
  `async load() {
          this.data = ${JSON.stringify(data)};
          this.loading = false;
        }`
);

if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(path.join(OUT_DIR, 'index.html'), html);

// Save today's snapshot for tomorrow's comparison
const today = new Date().toISOString().slice(0, 10);
const snapPath = path.join(DATA_DIR, `xml_${today}.json`);
if (!fs.existsSync(snapPath)) {
  fs.writeFileSync(snapPath, JSON.stringify({ date: today, listings: listings.map(l => ({ ref: l.ref })) }));
  console.log(`Saved snapshot: xml_${today}.json`);
}

console.log(`Built: ${data.total} listings (${data.sale} sale, ${data.rent} rent), ${data.newCount} new, 109 agents → dist/index.html`);
