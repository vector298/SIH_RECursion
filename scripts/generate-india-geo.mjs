/**
 * Regenerates src/data/india-geo.js — the SVG path data for the national outline
 * and the state boundaries used by <IndiaMap />.
 *
 * Source: @amcharts/amcharts5-geodata
 *   - worldIndiaHigh.json → the national boundary as officially depicted by India
 *     (extent 68.16°E–97.34°E, 6.75°N–37.04°N, i.e. the full extent of Jammu &
 *     Kashmir and Ladakh, and the Andaman & Nicobar and Lakshadweep islands).
 *   - india2023Low.json  → the 2023 state / union-territory set, for interior lines.
 *
 * The dataset is NOT a runtime dependency — this script bakes the geometry into a
 * plain .js file. To regenerate:
 *
 *   npm i -D @amcharts/amcharts5-geodata
 *   node scripts/generate-india-geo.mjs
 *   npm remove @amcharts/amcharts5-geodata
 *
 * To swap in Survey of India data (recommended before any official deployment),
 * point WORLD/STATES at your own GeoJSON with the same [lon, lat] ring structure.
 */
import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const WORLD = require('@amcharts/amcharts5-geodata/json/worldIndiaHigh.json');
const STATES = require('@amcharts/amcharts5-geodata/json/india2023Low.json');

/* Equirectangular projection into a 0–100 viewBox.
   Must stay identical to project() in src/components/IndiaMap.jsx. */
const LON0 = 66, LON_SPAN = 33, LAT_TOP = 37.5, LAT_SPAN = 31.5;
const px = (lon) => ((lon - LON0) / LON_SPAN) * 100;
const py = (lat) => ((LAT_TOP - lat) / LAT_SPAN) * 100;

/* Ramer–Douglas–Peucker, in projected units so tolerance means screen distance. */
function rdp(pts, eps) {
  if (pts.length < 3) return pts;
  let idx = 0, max = 0;
  const [ax, ay] = pts[0], [bx, by] = pts[pts.length - 1];
  const dx = bx - ax, dy = by - ay;
  const len = Math.hypot(dx, dy) || 1;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = Math.abs((pts[i][0] - ax) * dy - (pts[i][1] - ay) * dx) / len;
    if (d > max) { max = d; idx = i; }
  }
  if (max <= eps) return [pts[0], pts[pts.length - 1]];
  return [...rdp(pts.slice(0, idx + 1), eps).slice(0, -1), ...rdp(pts.slice(idx), eps)];
}

/* A closed ring's endpoints coincide, which degenerates RDP's baseline — so cut the
   ring at the vertex farthest from its start and simplify the two chains separately. */
function simplifyRing(pts, eps) {
  const open = pts.length > 1 &&
    pts[0][0] === pts[pts.length - 1][0] && pts[0][1] === pts[pts.length - 1][1]
      ? pts.slice(0, -1) : pts;
  if (open.length < 4) return open;
  let far = 0, best = -1;
  for (let i = 1; i < open.length; i++) {
    const d = Math.hypot(open[i][0] - open[0][0], open[i][1] - open[0][1]);
    if (d > best) { best = d; far = i; }
  }
  const a = rdp(open.slice(0, far + 1), eps);
  const b = rdp([...open.slice(far), open[0]], eps);
  return [...a.slice(0, -1), ...b.slice(0, -1)];
}

const ringToPath = (ring, eps, minPts) => {
  const proj = ring.map(([lon, lat]) => [px(lon), py(lat)]);
  const s = simplifyRing(proj, eps);
  if (s.length < minPts) return '';
  return 'M' + s.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join('L') + 'Z';
};

const polysOf = (g) => (g.type === 'Polygon' ? [g.coordinates] : g.coordinates);

function featurePath(feature, eps, minPts) {
  return polysOf(feature.geometry)
    .flatMap((poly) => poly.map((ring) => ringToPath(ring, eps, minPts)))
    .filter(Boolean)
    .join(' ');
}

const india = WORLD.features.find((f) => f.id === 'IN' || f.properties.name === 'India');
if (!india) throw new Error('India feature not found in worldIndiaHigh.json');

// Outline: tight tolerance, keep even small islands (3-point rings).
const outline = featurePath(india, 0.05, 3);

// State interiors: looser tolerance — these are hairlines at 20% opacity.
const states = STATES.features
  .map((f) => featurePath(f, 0.12, 4))
  .filter(Boolean)
  .join(' ');

let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
polysOf(india.geometry).forEach((p) => p.forEach((r) => r.forEach(([lon, lat]) => {
  minX = Math.min(minX, px(lon)); maxX = Math.max(maxX, px(lon));
  minY = Math.min(minY, py(lat)); maxY = Math.max(maxY, py(lat));
})));

const out = `/* GENERATED FILE — do not edit by hand.
 * Run: node scripts/generate-india-geo.mjs
 * Source: @amcharts/amcharts5-geodata (worldIndiaHigh + india2023Low), projected
 * equirectangularly into a 0–100 viewBox by scripts/generate-india-geo.mjs.
 * National boundary as officially depicted by India.
 */

/** Bounding box of the outline in viewBox units. */
export const INDIA_BOX = { x: ${minX.toFixed(2)}, y: ${minY.toFixed(2)}, w: ${(maxX - minX).toFixed(2)}, h: ${(maxY - minY).toFixed(2)} };

/** National boundary — mainland, Andaman & Nicobar, Lakshadweep. */
export const INDIA_PATH = '${outline}';

/** State and union-territory boundaries (2023), for hairline interior detail. */
export const INDIA_STATES_PATH = '${states}';
`;

mkdirSync('src/data', { recursive: true });
writeFileSync('src/data/india-geo.js', out);

console.log('outline chars:', outline.length, '| states chars:', states.length);
console.log('bbox x', minX.toFixed(2), '→', maxX.toFixed(2), ' y', minY.toFixed(2), '→', maxY.toFixed(2));
console.log('wrote src/data/india-geo.js (', (out.length / 1024).toFixed(1), 'KB )');
