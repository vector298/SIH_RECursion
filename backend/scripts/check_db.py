"""Diagnose the database connection before starting the API.

    python scripts/check_db.py

Reports what the app will actually connect to, whether it can, and — when it
cannot — what specifically is wrong. Connection problems on a fresh Postgres
install are almost always one of four things, and the error text alone rarely
says which.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text                      # noqa: E402

from app.config import settings                           # noqa: E402


def redacted(url: str) -> str:
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host = rest.rsplit("@", 1)
    user = creds.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


DIAGNOSES = [
    ("password authentication failed",
     "Wrong username or password. Check the credentials in backend/.env against\n"
     "  the ones you set when installing PostgreSQL. On a default install the user\n"
     "  is 'postgres'."),
    ("could not connect to server",
     "PostgreSQL is not running, or not listening on that host/port.\n"
     "  Windows:  services.msc -> find 'postgresql-x64-16' -> Start\n"
     "  Linux:    sudo service postgresql start"),
    ("connection refused",
     "Nothing is accepting connections on that port. PostgreSQL is likely stopped,\n"
     "  or running on a different port (5433 is common when two versions are installed).\n"
     "  Check with:  psql -U postgres -c \"SHOW port;\""),
    ("does not exist",
     "The database or role named in the URL does not exist. Create it with:\n"
     "  createdb -U postgres personmatch"),
    ("no password supplied",
     "The server wants a password but the URL has none. Add it to the URL in\n"
     "  backend/.env as postgresql+psycopg://user:PASSWORD@host:5432/dbname"),
    ("no module named 'psycopg'",
     "The PostgreSQL driver is missing. Install it with:\n"
     "  pip install \"psycopg[binary]\""),
]


def main() -> int:
    url = settings.database_url
    kind = "SQLite" if settings.is_sqlite else "PostgreSQL"

    print(f"target   : {redacted(url)}")
    print(f"engine   : {kind}")
    if settings.is_sqlite:
        print("\nnote     : this is the built-in fallback, not PostgreSQL.")
        print("           Set CASEINTEL_DATABASE_URL in backend/.env to use Postgres.")

    try:
        from app.db.session import engine

        with engine.connect() as conn:
            if not settings.is_sqlite:
                version = conn.execute(text("SELECT version()")).scalar_one()
                print(f"server   : {str(version).split(',')[0]}")

            tables = sorted(inspect(conn).get_table_names())
            print(f"\nconnected. {len(tables)} table(s) present.")

            if not tables:
                print("\nThe schema has not been created yet. Run:")
                print("  python -m app.seed --records 1500 --reset")
                return 0

            for name in tables:
                count = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar_one()
                print(f"  {name:22} {count:>8,}")

            cases = conn.execute(text("SELECT COUNT(*) FROM cases")).scalar_one() if "cases" in tables else 0
            if cases == 0:
                print("\nSchema exists but there are no records. Seed it with:")
                print("  python -m app.seed --records 1500 --reset")

    except Exception as exc:                                # noqa: BLE001
        message = str(exc)
        print(f"\nFAILED: {type(exc).__name__}")
        print(f"  {message.splitlines()[0][:200]}")

        lowered = message.lower()
        for needle, advice in DIAGNOSES:
            if needle in lowered:
                print(f"\nLikely cause:\n  {advice}")
                break
        else:
            print("\nNo specific diagnosis. Check that PostgreSQL is running and that\n"
                  "CASEINTEL_DATABASE_URL in backend/.env is correct.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
