# CASE//INTEL — Missing Person & Unidentified Person Case Intelligence

AI-assisted case intelligence for missing and unidentified person investigations:
a React investigation console and a FastAPI matching service. **All case data is
fictional**, and nothing in the system ever presents an AI output as a confirmed
identification.

```
caseintel/
├── src/            React console (this README)
├── backend/        FastAPI service — see backend/README.md
├── standalone/     one-file build, opens by double-click
└── docker-compose.yml
```

## The two halves

The frontend runs **with or without** the backend, and says which:

| | Backend running | Backend absent |
|---|---|---|
| Top bar | `API CONNECTED` + live model backends | `SAMPLE DATA` |
| Rankings, timings, funnel | Computed from the real index | Fictional sample values |
| Case creation | Persisted, then matchable | Captured locally, not saved |
| Mark extraction | Gemini, or the rule-based fallback | Local parse |

That is deliberate: the standalone single-file build has no server, and a demo
should degrade visibly rather than break. Anything on screen that is illustrative
rather than computed is labelled as such.

To run the whole thing:

```bash
docker compose up --build                                    # API on :8000
docker compose exec api python -m app.seed --records 1500 --reset
npm install && npm run dev                                   # console on :5173
```

Or start the API by hand — see [backend/README.md](backend/README.md), which also
covers the matching pipeline, the ArcFace implementation, and why Gemini is used
for language rather than face identification.

## Run it

### Option A — just look at it (no install, no Node)

Open **`standalone/CASE-INTEL.html`** in any modern browser — double-click it, or drag it
onto a browser window. It is the whole application inlined into one file: no server, no
build step, no internet connection needed (it falls back to system fonts offline). This is
the fastest path for a demo or an evaluator.

### Option B — run the source

```bash
npm install
npm run dev            # http://localhost:5173  — hot reload
npm run build          # → dist/          production build, serve with any static server
npm run build:single   # → dist-single/index.html   regenerates the standalone file
npm run lint
```

Requires **Node.js 20.19+ or 22.12+** (Vite 8). Check with `node -v`; if it's older,
install the current LTS from nodejs.org. Works on Windows, macOS and Linux — no
platform-specific scripts.

`npm ci` also works and is preferred for a reproducible install (`package-lock.json` is
included).

No backend is required. The UI runs entirely on the sample data in `src/data/sample.js`,
with the AI stages simulated at realistic timings.

> `dist/` and `node_modules/` are not in this archive — `npm install` recreates
> `node_modules`, and either build script recreates `dist/`.

## Stack

React 19 · Vite · Recharts · lucide-react · hand-written CSS design system
(no UI framework, no Tailwind).

## Structure

```
src/
  styles/theme.css      design tokens, primitives, motion
  styles/app.css        component + page styles
  data/sample.js        all fictional case, candidate, pipeline and analytics data
  components/
    Backdrop.jsx        ambient contour/node field behind the app
    TopNav.jsx          navigation, notifications, system status, officer profile
    HeroVisual.jsx      landing map + embedding + ranking composition
    IndiaMap.jsx        schematic national outline + lon/lat projection helper
    Portrait.jsx        anonymised abstract subject rendering (never a real/fake face)
    MetricCard.jsx      animated metric tile with sparkline and trend
    CaseCard.jsx        case tile with hover reveal and quick actions
    UncertainField.jsx  the Exact / Range / Unknown field primitive
    ui.jsx              Reveal, Counter, ConfidenceRing, EvidenceBar, Badge, Tip, …
  pages/
    Landing.jsx         hero + how-it-works
    Dashboard.jsx       Investigation Command Center
    Cases.jsx           filterable case register
    NewCase.jsx         7-step uncertainty-aware intake wizard
    MatchIntelligence.jsx  pipeline, hard-search funnel, ranked candidates
    Method.jsx          uncertainty / semantic / facial-quality / time-aware explainers
    Comparison.jsx      split-screen evidence comparison + adaptive investigation
    CaseDetail.jsx      case file with 6 tabs and investigation timeline
    Geospatial.jsx      map of cases, clusters and matched pairs
    Analytics.jsx       intelligence analytics charts
```

## Product concepts, and where each one is actually implemented

| Concept | UI | Backend |
| --- | --- | --- |
| Centralised cross-state index | Dashboard · Geospatial map | `db/models.py`, PostgreSQL |
| Uncertainty-aware fields | New Case wizard · Method tab | `core/uncertainty.py` |
| Hard search to reduce search space | Match Intelligence funnel | `core/hard_search.py` |
| Weighted evidence scoring | Evidence weights · Comparison | `core/fusion.py` |
| Time-aware matching & child growth | Method → Time-aware | `core/temporal.py` |
| Free-text semantic comparison | Method → Semantic | `core/semantic.py` |
| Structured extraction from free text | New Case step 05 | `services/gemini.py` |
| Facial embeddings | New Case step 06 | `services/face.py`, `core/arcface.py` |
| Image quality assessment | New Case step 06 · Method | `core/quality.py` |
| Ranked candidate results | Top Potential Matches | `core/pipeline.py` |
| Adaptive investigation questions | Comparison → Adaptive | `core/adaptive.py` |
| Human-in-the-loop verification | Persistent notice · Verify / Reject | `POST /api/cases/{id}/verify` |

## Map data

The national outline and state boundaries in `src/data/india-geo.js` are **generated**,
not hand-drawn. `scripts/generate-india-geo.mjs` reads GeoJSON from
`@amcharts/amcharts5-geodata` (`worldIndiaHigh` for the national boundary,
`india2023Low` for the 2023 state/UT set), projects it equirectangularly into the 0–100
viewBox the app draws in, simplifies it with Ramer–Douglas–Peucker, and writes the SVG
paths out as a plain `.js` file. The dataset is therefore **not a runtime or install
dependency** — the geometry ships baked in.

The boundary follows the extent officially depicted by India: 68.16°E–97.34°E,
6.75°N–37.04°N, covering the full extent of Jammu & Kashmir and Ladakh, plus the
Andaman & Nicobar and Lakshadweep islands. To regenerate, or to swap in Survey of India
data before any official deployment:

```bash
npm i -D @amcharts/amcharts5-geodata
node scripts/generate-india-geo.mjs
npm remove @amcharts/amcharts5-geodata
```

Case locations are stored as real longitude/latitude in `MAP_POINTS` and projected at
render time by `project()` in `src/components/IndiaMap.jsx`, so markers stay correctly
placed if the underlying geometry is replaced. Keep that function in step with the
projection constants at the top of the generator script.

## Notes on the imagery

Subject imagery is drawn as abstract, seeded SVG silhouettes rather than photographs.
A demonstration build of a missing-persons system should not display invented faces
attached to invented case records, and the abstraction also stands in honestly for the
biometric pipeline (the landmark overlay represents the embedding stage). Facial vectors
are described in the UI but never rendered as raw numbers.

## Wiring it to a backend

Replace `src/data/sample.js` with API calls. The shapes the UI expects:

- `CASES[]` — case records, with `ageMode`/`heightMode` of `exact` | `range` and
  `Unknown` permitted on any scalar field.
- `CANDIDATES[]` — ranked results carrying `confidence` plus a `scores` object
  (`face`, `marks`, `demographic`, `time`, `quality`, `location`), an `evidence[]`
  narrative and a `concerns[]` list.
- `PIPELINE[]` / `FUNNEL[]` — stage timings and search-space counts returned by the
  matching run, so the animation reflects real execution rather than fixed values.
