#!/usr/bin/env node
// Build static dashboard: embeds latest data into index.html, pushes to GitHub Pages
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DATA_DIR = path.join(__dirname, '..', 'huspy-tracker', 'data');
const TEMPLATE = path.join(__dirname, 'public', 'index.html');
const OUT_DIR = path.join(__dirname, 'dist');

function getSnapshotFiles() {
  return fs.readdirSync(DATA_DIR)
    .filter(f => /^\d{4}-\d{2}-\d{2}\.json$/.test(f))
    .sort();
}

function loadSnapshot(filename) {
  return JSON.parse(fs.readFileSync(path.join(DATA_DIR, filename), 'utf8'));
}

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

function agentLevel(listing) {
  if (listing.promo === 'Signature') return 'Signature';
  if (listing.promo === 'Hot') return 'Hot';
  if (listing.trubroker) return 'TruBroker';
  if (listing.verified) return 'Verified';
  return 'Standard';
}

function buildData() {
  const files = getSnapshotFiles();
  if (files.length === 0) return null;

  const latest = loadSnapshot(files[files.length - 1]);
  const latestDate = files[files.length - 1].replace('.json', '');
  let prev = null, prevDate = null;
  if (files.length >= 2) {
    prev = loadSnapshot(files[files.length - 2]);
    prevDate = files[files.length - 2].replace('.json', '');
  }

  const listings = latest.listings;
  let newListings = [];
  if (prev) {
    const prevIds = new Set(prev.listings.map(l => l.listing_id));
    newListings = listings.filter(l => !prevIds.has(l.listing_id));
  }

  const byArea = {};
  const byPrice = {};
  const byAgent = {};
  for (const l of newListings) {
    byArea[l.community || 'Unknown'] = (byArea[l.community || 'Unknown'] || 0) + 1;
    const key = `${l.purpose}|${priceBand(l.price_num, l.purpose)}`;
    byPrice[key] = (byPrice[key] || 0) + 1;
    const level = agentLevel(l);
    byAgent[level] = (byAgent[level] || 0) + 1;
  }

  const salePriceBands = {}, rentPriceBands = {};
  for (const [k, v] of Object.entries(byPrice)) {
    const [purpose, band] = k.split('|');
    if (purpose === 'sale') salePriceBands[band] = v;
    else rentPriceBands[band] = v;
  }

  const newIdSet = new Set(newListings.map(l => l.listing_id));
  const mapL = (l, isNew) => ({
    id: l.listing_id, community: l.community, sub_community: l.sub_community,
    type: l.type, bedrooms: l.bedrooms, price: l.price_num,
    priceFormatted: l.price, purpose: l.purpose, agent: l.agent,
    agentLevel: agentLevel(l), priceBand: priceBand(l.price_num, l.purpose),
    url: l.url, isNew,
    hasAgent: !!l.agent,
  });

  const removedCount = prev ? prev.listings.filter(l => !new Set(latest.listings.map(x=>x.listing_id)).has(l.listing_id)).length : 0;

  // Load agent registry if available
  const regPath = path.join(DATA_DIR, 'agent_registry.json');
  const agentRegistry = fs.existsSync(regPath) ? JSON.parse(fs.readFileSync(regPath, 'utf8')) : [];

  return {
    latestDate, prevDate,
    total: listings.length,
    sale: listings.filter(l => l.purpose === 'sale').length,
    rent: listings.filter(l => l.purpose === 'rent').length,
    newCount: newListings.length,
    removedCount,
    agentRegistry,
    byArea: Object.entries(byArea).sort((a, b) => b[1] - a[1]),
    salePriceBands, rentPriceBands, byAgentLevel: byAgent,
    newListings: newListings.map(l => mapL(l, true)),
    allListings: listings.map(l => mapL(l, newIdSet.has(l.listing_id))),
  };
}

// Build
const data = buildData();
if (!data) { console.error('No snapshot data'); process.exit(1); }

let html = fs.readFileSync(TEMPLATE, 'utf8');

// Replace the fetch-based load() with embedded data
html = html.replace(
  /async load\(\) \{[\s\S]*?this\.loading = false;\s*\}/,
  `async load() {
          this.data = ${JSON.stringify(data)};
          this.loading = false;
        }`
);

if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(path.join(OUT_DIR, 'index.html'), html);
console.log(`Built: ${data.total} listings, ${data.newTotal} new → dist/index.html`);
