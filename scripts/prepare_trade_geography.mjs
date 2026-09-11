import fs from 'node:fs';
import countries from 'world-countries';

const input = process.argv[2];
if (!input) throw new Error('Provide the downloaded Natural Earth GeoJSON path.');
const names = new Intl.DisplayNames(['ko'], { type: 'region', style: 'short' });
const metadata = countries.map(c => ({ code: c.cca2, name: names.of(c.cca2), lat: c.latlng[0], lon: c.latlng[1], region: c.region }));
const geo = JSON.parse(fs.readFileSync(input, 'utf8'));
const features = geo.features.filter(f => f.properties.ISO_A2_EH !== 'AQ').map(f => ({
  id: f.properties.ISO_A2_EH, geometry: f.geometry, properties: { name: f.properties.NAME }
}));
fs.writeFileSync('data/trade/countries.json', JSON.stringify(metadata));
fs.writeFileSync('data/trade/borders.json', JSON.stringify(features));
fs.copyFileSync('node_modules/world-countries/LICENSE', 'data/trade/COUNTRIES-LICENSE.md');
console.log(`Prepared ${metadata.length} locations and ${features.length} country borders.`);
