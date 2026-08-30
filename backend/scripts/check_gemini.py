"""Verify the Gemini API key end to end, before you rely on it in a demo.

    python scripts/check_gemini.py

`/api/health` reports `gemini_configured: true` as soon as a key is *present* —
it does not prove the key *works*. This script makes real calls and separates
the four states that look alike from the outside:

    no key set          -> the app runs on deterministic fallbacks, by design
    key set but invalid -> health says "configured", every call quietly degrades
    key valid, no quota -> works now, fails under load
    key valid and live  -> extraction and embeddings actually come from Gemini

Nothing here writes to the database. The key is never printed.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx                                                     # noqa: E402

from app.config import settings                                  # noqa: E402
from app.services.gemini import GeminiProvider                   # noqa: E402
from app.services.nlp import NlpClient, cosine, lexical_similarity  # noqa: E402

SAMPLE = ("A scar above his left eyebrow and a tattoo of a star on his right "
          "forearm. He was last seen wearing a blue shirt.")

# Same meaning, almost no shared vocabulary — the pair that shows whether
# embeddings are doing anything a word-overlap metric could not.
PARA_A = "star tattoo on right forearm"
PARA_B = "tattoo resembling a five-pointed star on the right arm"

OK, WARN, BAD = "  ok  ", " warn ", " FAIL "


def line(state: str, label: str, detail: str = "") -> None:
    print(f"[{state}] {label}" + (f"  {detail}" if detail else ""))


def fingerprint(key: str) -> str:
    """Enough to tell two keys apart in a screenshot. Not enough to use one."""
    return f"{key[:6]}…{key[-4:]}  ({len(key)} chars)"


STATUS_ADVICE = {
    400: "Malformed request, or a model name this key cannot use. Check\n"
         "       CASEINTEL_GEMINI_MODEL / CASEINTEL_GEMINI_EMBED_MODEL.",
    401: "The key was rejected. Check for a stray quote, a trailing space, or a\n"
         "       key copied only partly. Google keys start with 'AIza'.",
    403: "The key is refused for this API. Usually: the Generative Language API\n"
         "       is not enabled on that project, or the key has referrer/IP\n"
         "       restrictions. A key from https://aistudio.google.com/apikey has\n"
         "       neither by default.",
    404: "That model has been retired, or was never available to this key. The\n"
         "       provider substitutes the nearest equivalent automatically; this\n"
         "       only fails outright when nothing suitable is reachable.",
    429: "Quota or rate limit. The key is valid; you are out of requests for now.\n"
         "       The app degrades to rules and lexical comparison until it clears.",
}


def main() -> int:                                               # noqa: C901
    key = settings.gemini_api_key
    print(f"env file : {Path(settings.model_config['env_file'])}")
    print(f"model    : {settings.gemini_model}")
    print(f"embed    : {settings.gemini_embed_model}")
    print(f"timeout  : {settings.gemini_timeout_s:.0f}s\n")

    if not key:
        line(WARN, "no key set", "CASEINTEL_GEMINI_API_KEY is empty")
        print("\n  The service still runs: extraction falls back to rules and")
        print("  semantic comparison to lexical overlap, and every response says so.")
        print("\n  To use Gemini, edit backend/.env, remove the leading '#' from")
        print("  the CASEINTEL_GEMINI_API_KEY line, paste your key after the '=',")
        print("  and restart the API. Settings are cached at import, so an already")
        print("  running uvicorn will not pick up the change.")
        return 1

    line(OK, "key present", fingerprint(key))
    if key != key.strip() or key.startswith(("'", '"')):
        line(WARN, "suspicious key text", "surrounding quotes or whitespace — .env needs neither")

    provider = GeminiProvider()
    failures = 0

    # -- 1. does the key authenticate at all -------------------------------
    # ListModels is the cheapest call that separates "bad key" from "bad model".
    try:
        started = time.perf_counter()
        with httpx.Client(timeout=settings.gemini_timeout_s) as client:
            response = client.get(f"{settings.gemini_base_url.rstrip('/')}/models",
                                  headers={"x-goog-api-key": key})
        elapsed = (time.perf_counter() - started) * 1000
    except httpx.TimeoutException:
        line(BAD, "authentication", f"timed out after {settings.gemini_timeout_s:.0f}s")
        print("\n  No answer from Google. Check network access, a proxy, or a firewall.")
        return 1
    except httpx.HTTPError as exc:
        line(BAD, "authentication", f"{type(exc).__name__}: {exc}")
        print("\n  The request never reached Google. This is a network problem, not a key problem.")
        return 1

    if response.status_code != 200:
        line(BAD, "authentication", f"HTTP {response.status_code} in {elapsed:.0f}ms")
        advice = STATUS_ADVICE.get(response.status_code)
        if advice:
            print(f"\n  Cause: {advice}")
        print(f"\n  Google said: {response.text[:300]}")
        return 1

    catalogue = provider.catalogue()
    line(OK, "authentication", f"HTTP 200 in {elapsed:.0f}ms, {len(catalogue)} models visible")

    def report_model(kind: str, wanted: str) -> None:
        """What the provider settled on, after the call proved it works.

        Deliberately reported *after* the call rather than from ListModels: a
        model can be listed and still answer 404 on use, which is exactly how
        gemini-2.5-flash behaves for keys issued after it closed. Only the call
        is evidence.
        """
        chosen = provider.resolve(kind)
        if chosen and chosen != wanted:
            setting = "CASEINTEL_GEMINI_EMBED_MODEL" if kind == "embed" else "CASEINTEL_GEMINI_MODEL"
            line(WARN, f"{kind} model", f"{wanted} is unavailable — using {chosen}")
            print(f"       Pin it with {setting}={chosen} in backend/.env so the")
            print("       demo cannot shift under you mid-presentation.")

    def report_unavailable(kind: str, method: str) -> None:
        options = sorted(n for n, methods in catalogue.items() if method in methods)
        line(BAD, f"{kind} model", f"nothing reachable supports {method}")
        if options:
            print(f"       this key can reach: {', '.join(options[:6])}")

    # -- 2. embeddings ------------------------------------------------------
    started = time.perf_counter()
    vector = provider.embed(PARA_A)
    elapsed = (time.perf_counter() - started) * 1000
    if vector:
        line(OK, "embedding", f"{len(vector)}-D vector from "
                              f"{provider.resolve('embed')} in {elapsed:.0f}ms")
        report_model("embed", settings.gemini_embed_model)
    else:
        failures += 1
        line(BAD, "embedding", "returned nothing — see the log line above for the reason")
        report_unavailable("embed", "embedContent")

    # -- 3. structured extraction ------------------------------------------
    started = time.perf_counter()
    features = NlpClient(provider).extract_features(SAMPLE)
    elapsed = (time.perf_counter() - started) * 1000

    if features.source == "gemini" and not features.degraded:
        line(OK, "extraction", f"{len(features.marks)} mark(s) from "
                               f"{provider.resolve('chat')} in {elapsed:.0f}ms")
        report_model("chat", settings.gemini_model)
    else:
        failures += 1
        line(BAD, "extraction", f"source={features.source} degraded={features.degraded}")
        report_unavailable("chat", "generateContent")
        for warning in features.warnings:
            print(f"       {warning}")
        print("       The rule-based extractor answered instead. The request still")
        print("       succeeded — that is the fallback working, not a crash.")

    for mark in features.marks:
        print(f"       - {mark.canonical_text()}")

    # -- 4. is it actually better than the fallback -------------------------
    lex = lexical_similarity(PARA_A, PARA_B)
    if vector:
        other = provider.embed(PARA_B)
        if other and len(other) == len(vector):
            emb = max(0.0, (cosine(vector, other) + 1.0) / 2.0)
            verdict = OK if emb > lex else WARN
            line(verdict, "paraphrase pair", f"lexical {lex:.3f}  ->  embedding {emb:.3f}")
            print(f"       \"{PARA_A}\"")
            print(f"       \"{PARA_B}\"")
            if emb <= lex:
                print("       Embeddings scored no higher than word overlap here. Not a")
                print("       failure, but worth a second example before trusting it.")
        else:
            line(WARN, "paraphrase pair", "second embedding failed; skipped")

    # -- verdict ------------------------------------------------------------
    print()
    if failures:
        print(f"{failures} check(s) failed. The API will keep serving requests on the")
        print("deterministic fallbacks; run `uvicorn` and watch the log for the")
        print("specific Gemini error each time a call degrades.")
        return 1

    print("Key is linked and working. Confirm the running service agrees:")
    if sys.platform.startswith("win"):
        # PowerShell aliases curl to Invoke-WebRequest, where these flags mean
        # something else entirely. Give the native call instead.
        print("  Invoke-RestMethod http://localhost:8000/api/health |"
              " Select-Object -Expand backends")
        print("  Invoke-RestMethod -Method Post http://localhost:8000/api/marks/extract `")
        print("    -ContentType application/json `")
        print(f"    -Body '{{\"text\": \"{SAMPLE}\"}}' |"
              " Select-Object source, degraded, embedding_model, embedding_dim")
    else:
        print("  curl http://localhost:8000/api/health")
        print("  curl -X POST http://localhost:8000/api/marks/extract \\")
        print("       -H 'content-type: application/json' \\")
        print(f"       -d '{{\"text\": \"{SAMPLE}\"}}'")
    print("\nIn that response, source must be \"gemini\" and degraded false. If the")
    print("script passes but the endpoint says \"rules\", the server is running with")
    print("older settings — restart uvicorn.")
    print("\nThen bring the stored corpus onto this embedding model, so mark")
    print("comparison uses embeddings rather than falling back to word overlap:")
    print("  python scripts/reembed_marks.py --dry-run")
    print("  python scripts/reembed_marks.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
