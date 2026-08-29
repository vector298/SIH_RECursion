import os
import tempfile
from pathlib import Path

# Point the app at a throwaway database *before* anything imports settings.
_TMP = Path(tempfile.mkdtemp(prefix="caseintel-test-"))
os.environ["CASEINTEL_DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["CASEINTEL_MEDIA_ROOT"] = str(_TMP / "media")
os.environ.pop("CASEINTEL_GEMINI_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    init_db()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def tmp_media():
    path = _TMP / "media"
    path.mkdir(parents=True, exist_ok=True)
    return path
