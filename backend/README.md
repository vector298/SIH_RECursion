# CASE//INTEL — backend

FastAPI service behind the investigation console: an uncertainty-aware case
store, a seven-stage matching pipeline, and the officer-decision endpoints.

**The service ranks and explains. It never asserts an identification.** There is
no code path by which software alone sets an identity on a case.

---

## Run it

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m app.seed --records 1500 --reset              # fictional corpus
uvicorn app.main:app --reload
```

Docs at http://localhost:8000/docs. **Start with `GET /api/health`** — it reports
which model backends are actually live, so you know before a demo whether you
are on real ArcFace weights and a Gemini key or on the local fallbacks.

Requires Python 3.11+. SQLite by default; set `CASEINTEL_DATABASE_URL` for
PostgreSQL. Or run the whole stack:

```bash
docker compose up --build
docker compose exec api python -m app.seed --records 1500 --reset
```

### Optional model backends

```bash
pip install -r requirements-models.txt   # InsightFace ArcFace + sentence-transformers
pip install -r requirements-train.txt --index-url https://download.pytorch.org/whl/cpu
cp .env.example .env                     # add CASEINTEL_GEMINI_API_KEY
```

Nothing above is required. Every one has a local fallback and the API reports
which is in use.

---

## The pipeline

| # | Stage | What it does |
|---|-------|--------------|
| 01 | Data ingestion | Normalises the probe; resolves exact / range / unknown modes |
| 02 | Hard search | Indexed SQL reduction — sex, time window, geographic box |
| 03 | Attribute filtering | Interval comparison with time-projected ages |
| 04 | Semantic comparison | Identification-mark descriptions via embeddings |
| 05 | Facial comparison | ArcFace embeddings, cosine similarity |
| 06 | Quality adjustment | Image quality caps facial evidence |
| 07 | Confidence ranking | Weighted fusion, shrunk by evidence coverage |

Stage timings in the response are measured and funnel counts are the real
surviving set sizes. Nothing is scripted.

---

## Four decisions worth knowing about

### 1. Unknown is not zero

Every bounded attribute is stored as `(mode, lo, hi)`: exact collapses to
`lo == hi`, unknown is `NULL`. Comparing anything against unknown returns
`None`, not `0.0` — "no evidence" rather than "evidence against". Fusion drops
`None` sources from the weighted mean and reports the resulting **coverage**.

A sparse record scores lower because it carries less evidence, never because a
blank field was read as a mismatch. Every SQL predicate in the hard search is
written so `NULL` cannot exclude a row. This is the property the whole system
rests on, and `tests/test_uncertainty.py` pins it down.

To stop a thin record winning on one lucky attribute, the weighted mean is
shrunk toward neutral in proportion to missing coverage.

### 2. Facial evidence is weighted by how much it has earned

Two independent scalings apply before facial similarity reaches the ranking:

* **Image quality** — the *lower* of the two image qualities caps the score. A
  0.97 cosine off a blurred 80×80 crop is not 0.97 of evidence.
* **Backend reliability** — measured, not assumed. `scripts/calibrate_face.py`
  reports the equal error rate of whichever backend is loaded, and
  `services/face.CALIBRATION` turns that into a weight multiplier.

The bundled fallback descriptor measures **EER 0.47, ROC AUC 0.61** — barely
above chance, which is what an unsupervised descriptor should score. Its
reliability is therefore `0.08`: facial similarity contributes almost nothing
until real ArcFace weights are installed, and `/api/health` and every match
response say so. Dressing up a coin flip as biometric evidence is how an
investigative tool sends officers to the wrong address.

### 3. ArcFace: the loss and the inference are different things

`app/core/arcface.py` has both, deliberately separated:

* `ArcMarginProduct` / `ArcFaceLoss` — the **training** head. Normalises
  embedding and class weights onto a hypersphere, adds angular margin `m` to
  the ground-truth angle, scales by `s`, then softmax cross-entropy. Includes
  the monotonicity guard for `θ + m > π`. Verified against an independent NumPy
  reference in `tests/test_arcface.py` (agreement to 1e-4, margin penalises only
  the target class, `m=0` degenerates to plain scaled cosine).
* **Inference** never touches the loss: take the trained backbone's 512-D
  output, L2-normalise, compare by cosine.

### 4. Gemini does language, not identity

Gemini handles structured extraction from free-text marks, text embeddings,
evidence narratives, and image quality / soft-attribute reads.

It does **not** do face identification. It exposes no face-embedding endpoint,
and identifying individuals from photographs is outside its acceptable-use
policy — such prompts get refused. Identity comparison is ArcFace's job. The
narrative endpoint is given scores the deterministic pipeline already computed
and is instructed to phrase them; it cannot change a ranking.

---

## API

| Method | Path | |
|---|---|---|
| `POST` | `/api/cases` | Create a case with uncertainty-aware attributes |
| `GET` | `/api/cases` | Search and filter |
| `GET` | `/api/cases/{id}` | Full record (`id` or case number) |
| `POST` | `/api/cases/{id}/marks` | Add an identification mark (embedded on write) |
| `POST` | `/api/cases/{id}/images` | Upload → quality assessment → face embedding |
| `POST` | `/api/marks/extract` | Free text → structured fields |
| `POST` | `/api/cases/{id}/match` | Run the pipeline |
| `POST` | `/api/matches/{run}/answer` | Fold an officer's answer into the ranking |
| `POST` | `/api/cases/{id}/verify` | Record verify / reject / request-evidence |
| `GET` | `/api/health` | Live backends and counts |
| `GET` | `/api/analytics/*` | Summary, by-state, confidence distribution, map |

Face embeddings are persisted but **never serialised** — the API returns
similarity scores, not biometric vectors.

---

## Tests

```bash
pip install -r requirements-train.txt   # pytest, and torch for the ArcFace tests
python -m pytest -q                     # 107 passed
```

Covering interval semantics and unknown-neutrality, fusion and coverage
shrinkage, quality capping, time projection and weight decay, the ArcFace loss
against its NumPy reference, semantic mark comparison including side conflicts,
adaptive question generation, and the full API flow.

Two bugs the suite caught during development, both left as regression tests:
noise defeating a Laplacian-variance blur metric (`test_noise_cannot_masquerade_as_sharpness`),
and evidence narratives quoting different intervals from the ones actually scored.

---

## Layout

```
app/
  config.py            settings; every model backend optional
  db/models.py         uncertainty-aware ORM
  schemas.py           API contracts
  core/
    uncertainty.py     Interval, exact/range/unknown, comparison
    temporal.py        age projection, attribute weight decay
    geo.py             distance scored against elapsed time
    semantic.py        mark comparison; Gemini → ST → lexical
    arcface.py         ArcFace loss (torch + numpy reference), cosine helpers
    quality.py         noise-robust blur, exposure, resolution, visibility
    fusion.py          weighted fusion, coverage shrinkage, quality cap
    hard_search.py     indexed SQL reduction with funnel counts
    adaptive.py        targeted questions, officer answer folding
    pipeline.py        the seven stages
  services/
    face.py            InsightFace ArcFace + calibrated fallback
    gemini.py          extraction, embeddings, narratives, image description
  synthetic.py         drawn portraits for seeding and tests
  seed.py              fictional corpus
scripts/
  calibrate_face.py    measure EER / AUC, print the calibration entry
  generate-india-geo.mjs   (frontend map geometry — see ../README.md)
```

---

## Data

All seeded data is fictional. No real case, person, name or photograph is
represented. Seed portraits are drawn shapes, not generated likenesses — a
demonstration corpus should not contain invented faces attached to invented
case records.

Before any real deployment: add authentication and per-jurisdiction
authorisation (there is none — every endpoint is open), encrypt embeddings at
rest, put the media directory behind object storage with signed URLs, and have
the retention and consent model reviewed against the DPDP Act.
