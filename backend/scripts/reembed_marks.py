"""Re-embed stored identification marks after an embedding-model change.

    python scripts/reembed_marks.py --dry-run     # what would change
    python scripts/reembed_marks.py               # do it

Vectors from two different embedding models cannot be compared — the same
sentence lands in unrelated coordinate systems, and when the dimensions happen
to agree there is nothing in the numbers to reveal the mistake. The matcher
therefore refuses mismatched pairs and falls back to lexical comparison, which
is safe but weaker.

So after adding a key, or after Google retires a model and the provider
substitutes another, the corpus holds vectors from the old model and quietly
stops using them. This brings them onto the current model.

Marks whose vector is already current are skipped, so the script is cheap to
re-run and safe to interrupt: it commits in batches and picks up where it left
off.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                # noqa: E402

from app.core import semantic                                # noqa: E402
from app.db.models import Mark                               # noqa: E402
from app.db.session import SessionLocal                      # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing")
    parser.add_argument("--batch", type=int, default=50,
                        help="commit every N marks (default 50)")
    parser.add_argument("--limit", type=int, default=0,
                        help="stop after N marks (0 = all)")
    args = parser.parse_args()

    target = semantic.backend_name()
    print(f"current embedding backend : {target}")

    if target.startswith("lexical"):
        print("\nNo embedding provider is configured, so there is nothing to re-embed.")
        print("Set CASEINTEL_GEMINI_API_KEY in backend/.env first, then verify with:")
        print("  python scripts/check_gemini.py")
        return 1

    with SessionLocal() as db:
        marks = list(db.scalars(select(Mark).order_by(Mark.id)))
        stale = [m for m in marks
                 if (m.description or "").strip() and m.embedding_model != target]

        print(f"marks in corpus           : {len(marks):,}")
        print(f"already on this model     : {len(marks) - len(stale):,}")
        print(f"to re-embed               : {len(stale):,}")

        if args.limit:
            stale = stale[:args.limit]
        if not stale:
            print("\nNothing to do.")
            return 0

        by_model: dict[str, int] = {}
        for mark in stale:
            by_model[mark.embedding_model or "(none)"] = \
                by_model.get(mark.embedding_model or "(none)", 0) + 1
        for name, count in sorted(by_model.items(), key=lambda kv: -kv[1]):
            print(f"    {count:>7,}  {name}")

        if args.dry_run:
            print("\nDry run — nothing written.")
            return 0

        print()
        started, done, failed = time.perf_counter(), 0, 0
        for index, mark in enumerate(stale, start=1):
            vector, model = semantic.embed(mark.description)
            if vector:
                mark.embedding, mark.embedding_model = vector, model
                done += 1
            else:
                # Leave the old vector in place: the matcher will not use it
                # against a current one, and an empty column is no better.
                failed += 1

            if index % args.batch == 0:
                db.commit()
                rate = index / max(time.perf_counter() - started, 1e-9)
                print(f"  {index:>7,} / {len(stale):,}   {rate:5.1f}/s   {failed} failed")

        db.commit()

    elapsed = time.perf_counter() - started
    print(f"\nre-embedded {done:,} mark(s) in {elapsed:.0f}s; {failed} could not be embedded.")
    if failed:
        print("The failures fell back to the deterministic path and are still matchable.")
        print("Re-run to retry them — a quota rejection clears on its own.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
