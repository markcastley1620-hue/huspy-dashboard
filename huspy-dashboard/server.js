const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 3800;
const DATA_DIR = path.join(__dirname, '..', 'huspy-tracker', 'data');

const MIME = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.json': 'application/json',
};

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
  // sale
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

function mapListing(l, isNew) {
  return {
    id: l.listing_id, community: l.community, sub_community: l.sub_community,
    type: l.type, bedrooms: l.bedrooms, price: l.price_num,
    priceFormatted: l.price, purpose: l.purpose, agent: l.agent,
    agentLevel: agentLevel(l), priceBand: priceBand(l.price_num, l.purpose),
    url: l.url, isNew: isNew,
    hasAgent: !!l.agent,
  };
}

function buildDashData() {
  const files = getSnapshotFiles();
  if (files.length === 0) return { error: 'No data' };

  const latest = loadSnapshot(files[files.length - 1]);
  const latestDate = files[files.length - 1].replace('.json', '');

  // Find previous snapshot
  let prev = null;
  let prevDate = null;
  if (files.length >= 2) {
    prev = loadSnapshot(files[files.length - 2]);
    prevDate = files[files.length - 2].replace('.json', '');
  }

  const listings = latest.listings;
  const sale = listings.filter(l => l.purpose === 'sale');
  const rent = listings.filter(l => l.purpose === 'rent');

  // New listings (IDs in latest not in previous)
  let newListings = [];
  let newIds = new Set();
  if (prev) {
    const prevIds = new Set(prev.listings.map(l => l.listing_id));
    newListings = listings.filter(l => !prevIds.has(l.listing_id));
    newIds = new Set(newListings.map(l => l.listing_id));
  }

  // Breakdowns for new listings
  const byArea = {};
  const byPrice = {};
  const byAgent = {};

  for (const l of newListings) {
    const area = l.community || 'Unknown';
    byArea[area] = (byArea[area] || 0) + 1;

    const band = priceBand(l.price_num, l.purpose);
    const key = `${l.purpose}|${band}`;
    byPrice[key] = (byPrice[key] || 0) + 1;

    const level = agentLevel(l);
    byAgent[level] = (byAgent[level] || 0) + 1;
  }

  // Sort area by count desc
  const areaSorted = Object.entries(byArea).sort((a, b) => b[1] - a[1]);

  // Separate price by purpose
  const salePriceBands = {};
  const rentPriceBands = {};
  for (const [k, v] of Object.entries(byPrice)) {
    const [purpose, band] = k.split('|');
    if (purpose === 'sale') salePriceBands[band] = v;
    else rentPriceBands[band] = v;
  }

  // Available dates for picker
  const dates = files.map(f => f.replace('.json', ''));

  return {
    latestDate,
    prevDate,
    total: listings.length,
    sale: sale.length,
    rent: rent.length,
    newTotal: newListings.length,
    newSale: newListings.filter(l => l.purpose === 'sale').length,
    newRent: newListings.filter(l => l.purpose === 'rent').length,
    byArea: areaSorted,
    salePriceBands,
    rentPriceBands,
    byAgentLevel: byAgent,
    dates,
    newCount: newListings.length,
    removedCount: prev ? prev.listings.filter(l => !new Set(listings.map(x=>x.listing_id)).has(l.listing_id)).length : 0,
    newListings: newListings.map(l => mapListing(l, true)),
    allListings: listings.map(l => mapListing(l, newIds.has(l.listing_id))),
  };
}

function buildCompareData(date1, date2) {
  const files = getSnapshotFiles();
  const f1 = `${date1}.json`;
  const f2 = `${date2}.json`;
  if (!files.includes(f1) || !files.includes(f2)) return { error: 'Date not found' };

  const snap1 = loadSnapshot(f1);
  const snap2 = loadSnapshot(f2);

  const ids1 = new Set(snap1.listings.map(l => l.listing_id));
  const newListings = snap2.listings.filter(l => !ids1.has(l.listing_id));

  const byArea = {};
  const byAgent = {};
  for (const l of newListings) {
    const area = l.community || 'Unknown';
    byArea[area] = (byArea[area] || 0) + 1;
    const level = agentLevel(l);
    byAgent[level] = (byAgent[level] || 0) + 1;
  }

  return {
    from: date1,
    to: date2,
    prevTotal: snap1.listings.length,
    currTotal: snap2.listings.length,
    newTotal: newListings.length,
    byArea: Object.entries(byArea).sort((a, b) => b[1] - a[1]),
    byAgentLevel: byAgent,
  };
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (url.pathname === '/api/dashboard') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(buildDashData()));
    return;
  }

  if (url.pathname === '/api/compare') {
    const d1 = url.searchParams.get('from');
    const d2 = url.searchParams.get('to');
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(buildCompareData(d1, d2)));
    return;
  }

  // Serve static files
  let filePath = path.join(__dirname, 'public', url.pathname === '/' ? 'index.html' : url.pathname);
  const ext = path.extname(filePath);
  if (!ext) filePath = path.join(__dirname, 'public', 'index.html');

  fs.readFile(filePath, (err, data) => {
    if (err) {
      fs.readFile(path.join(__dirname, 'public', 'index.html'), (e2, d2) => {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(d2);
      });
      return;
    }
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(data);
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Dashboard on http://0.0.0.0:${PORT}`);
});
