/**
 * CASE//INTEL API client.
 *
 * The app runs with or without the backend. When the API is reachable, every
 * screen shows computed results; when it is not, the app falls back to the
 * fictional sample data in src/data/sample.js and says so in the top bar.
 * That is deliberate — the standalone single-file build has no server, and a
 * demo should degrade visibly rather than break.
 *
 * Point it elsewhere with VITE_API_URL at build time.
 */
const BASE = (import.meta.env?.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(status, detail, url) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.url = url;
  }
}

async function request(path, { method = 'GET', body, signal, timeout = 20000, raw } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  if (signal) signal.addEventListener('abort', () => controller.abort(), { once: true });

  try {
    const res = await fetch(`${BASE}${path}`, {
      method,
      signal: controller.signal,
      headers: raw ? undefined : { 'content-type': 'application/json' },
      body: raw ? body : body != null ? JSON.stringify(body) : undefined,
    });

    if (res.status === 204) return null;

    const payload = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, payload?.detail ?? res.statusText, path);
    return payload;
  } finally {
    clearTimeout(timer);
  }
}

/* ---------------------------------------------------------------- meta --- */
export const getHealth = (signal) => request('/api/health', { signal, timeout: 4000 });

/* --------------------------------------------------------------- cases --- */
export function listCases({ caseType, state, priority, q, limit = 60 } = {}, signal) {
  const params = new URLSearchParams();
  if (caseType && caseType !== 'all') params.set('case_type', caseType);
  if (state && state !== 'All states') params.set('state', state);
  if (priority && priority !== 'All priorities') params.set('priority', priority);
  if (q) params.set('q', q);
  params.set('limit', String(limit));
  return request(`/api/cases?${params}`, { signal });
}

export const getCase = (id, signal) => request(`/api/cases/${encodeURIComponent(id)}`, { signal });
export const createCase = (payload) => request('/api/cases', { method: 'POST', body: payload });
export const deleteCase = (id) => request(`/api/cases/${id}`, { method: 'DELETE' });

export const addMark = (caseId, mark) =>
  request(`/api/cases/${caseId}/marks`, { method: 'POST', body: mark });

export function uploadImage(caseId, file, slot = 'face') {
  const form = new FormData();
  form.append('file', file);
  form.append('slot', slot);
  return request(`/api/cases/${caseId}/images`, { method: 'POST', body: form, raw: true, timeout: 60000 });
}

/* ------------------------------------------------------------ matching --- */
export const extractMark = (text, signal) =>
  request('/api/marks/extract', { method: 'POST', body: { text }, signal });

export const runMatch = (caseId, signal) =>
  request(`/api/cases/${encodeURIComponent(caseId)}/match`, { method: 'POST', signal, timeout: 60000 });

export const answerQuestion = (runId, chosenCaseId, officer) =>
  request(`/api/matches/${runId}/answer`, {
    method: 'POST',
    body: { chosen_case_id: chosenCaseId, officer },
  });

export const recordVerification = (caseId, payload) =>
  request(`/api/cases/${caseId}/verify`, { method: 'POST', body: payload });

export const listVerifications = (caseId, signal) =>
  request(`/api/cases/${caseId}/verifications`, { signal });

/* ----------------------------------------------------------- analytics --- */
export const analyticsSummary = (signal) => request('/api/analytics/summary', { signal });
export const analyticsByState = (signal) => request('/api/analytics/by-state', { signal });
export const analyticsConfidence = (signal) => request('/api/analytics/confidence-distribution', { signal });
export const analyticsMap = (signal) => request('/api/analytics/map', { signal });

export const API_BASE = BASE;

/* ------------------------------------------------------------ adapters --- */
/** Turn an API case record into the shape the existing UI components expect. */
export function adaptCase(record) {
  if (!record) return null;
  const age = record.age ?? {};
  const height = record.height ?? {};
  const city = (record.location_text || '').split(',')[0].trim();

  return {
    id: record.case_number,
    uuid: record.id,
    type: record.case_type,
    name: record.name,
    nameKnown: Boolean(record.name),
    ageMode: age.mode ?? 'unknown',
    ageExact: age.exact ?? undefined,
    ageMin: age.min ?? undefined,
    ageMax: age.max ?? undefined,
    heightMode: height.mode ?? 'unknown',
    heightExact: height.exact ?? undefined,
    heightMin: height.min ?? undefined,
    heightMax: height.max ?? undefined,
    sex: record.sex ?? 'Unknown',
    build: record.build ?? 'Unknown',
    bloodType: record.blood_type ?? 'Unknown',
    location: record.location_text ?? '—',
    city,
    district: record.district ?? '—',
    state: record.state ?? '—',
    lastSeen: (record.last_seen_at || '').slice(0, 10),
    lastSeenTime: (record.last_seen_at || '').slice(11, 16),
    coords: [record.lat, record.lon],
    priority: record.priority,
    status: record.status,
    matches: record.candidate_count ?? 0,
    confidence: Math.round((record.top_confidence ?? 0) * 100),
    circumstances: record.circumstances ?? '',
    clothing: record.clothing ?? '',
    marks: (record.marks ?? []).map((m) => ({
      kind: m.kind ?? 'Feature',
      location: m.body_location ?? '',
      side: m.side ?? '',
      size: m.size_text ?? '',
      shape: m.shape ?? '',
      text: m.description ?? '',
    })),
    imageQuality: (record.images ?? [])[0]?.quality_score ?? null,
    officer: record.officer ?? '—',
    opened: (record.created_at || '').slice(0, 10),
    live: true,
  };
}

/** Turn an API candidate into the shape the ranking and comparison UI expect. */
export function adaptCandidate(candidate) {
  const s = candidate.scores ?? {};
  const pct = (v) => (v == null ? null : Math.round(v * 100));

  return {
    rank: candidate.rank,
    id: candidate.case.case_number,
    uuid: candidate.case.id,
    label: candidate.case.case_type === 'missing' ? 'Missing Person' : 'Unidentified Person',
    name: candidate.case.name,
    ageText: formatUncertain(candidate.case.age),
    location: candidate.case.location_text ?? '—',
    date: (candidate.case.last_seen_at || '').slice(0, 10),
    confidence: Math.round((candidate.confidence ?? 0) * 100),
    coverage: candidate.coverage,
    seed: hashSeed(candidate.case.case_number),
    scores: {
      face: pct(s.face),
      marks: pct(s.marks),
      demographic: pct(s.demographic),
      time: pct(s.time),
      quality: pct(s.quality),
      location: pct(s.location),
    },
    sources: candidate.sources ?? {},
    detail: candidate.detail ?? {},
    evidence: candidate.evidence ?? [],
    concerns: candidate.concerns ?? [],
    confidenceBefore:
      candidate.confidence_before == null ? null : Math.round(candidate.confidence_before * 100),
    officerConfirmed: candidate.officer_confirmed ?? null,
    live: true,
  };
}

export function formatUncertain(value, unit = '') {
  if (!value || value.mode === 'unknown') return 'Unknown';
  const suffix = unit ? ` ${unit}` : '';
  if (value.mode === 'exact') return `${round(value.exact)}${suffix}`;
  return `${round(value.min)}–${round(value.max)}${suffix}`;
}

const round = (n) => (n == null ? '?' : Math.round(n * 10) / 10);

/** Stable portrait seed from a case number, so a record always looks the same. */
export function hashSeed(text) {
  let h = 2166136261;
  for (let i = 0; i < String(text).length; i++) {
    h ^= String(text).charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h) % 9973;
}
