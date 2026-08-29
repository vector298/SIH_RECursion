import { INDIA_PATH, INDIA_STATES_PATH, INDIA_BOX } from '../data/india-geo';

export { INDIA_PATH, INDIA_STATES_PATH, INDIA_BOX };

/**
 * Equirectangular projection into the 0–100 viewBox the outline is drawn in.
 * Case coordinates go through this, so markers land on the right part of the map.
 * Must stay in step with scripts/generate-india-geo.mjs.
 */
export const project = (lon, lat) => ({
  x: +(((lon - 66) / 33) * 100).toFixed(2),
  y: +(((37.5 - lat) / 31.5) * 100).toFixed(2),
});

/**
 * National outline, drawn from Natural-Earth-derived geodata that follows the
 * boundary as officially depicted by India — including the full extent of Jammu &
 * Kashmir and Ladakh, and the Andaman & Nicobar and Lakshadweep islands.
 * Simplified for display; not a survey-accurate boundary.
 */
export default function IndiaMap({
  fill = 'rgba(30,80,130,.16)',
  stroke = 'rgba(120,180,240,.34)',
  strokeWidth = 0.35,
  states = false,
  stateStroke = 'rgba(120,180,240,.16)',
  stateWidth = 0.18,
}) {
  return (
    <g>
      <path d={INDIA_PATH} fill={fill} stroke="none" />
      {states && (
        <path d={INDIA_STATES_PATH} fill="none" stroke={stateStroke} strokeWidth={stateWidth}
              strokeLinejoin="round" />
      )}
      <path d={INDIA_PATH} fill="none" stroke={stroke} strokeWidth={strokeWidth}
            strokeLinejoin="round" strokeLinecap="round" />
    </g>
  );
}
