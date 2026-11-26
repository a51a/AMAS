import shutil

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage.db import Database
from app.storage.repository import Repository
from app.taste_engine.profiles import ensure_exp001

HAS_FFMPEG = shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


@pytest.fixture
def settings(tmp_path):
    s = Settings(data_dir=tmp_path / "data", allow_external_providers=False, ocr="off", _env_file=None)
    s.ensure_dirs()
    return s


@pytest.fixture
def repo(settings):
    r = Repository(Database(settings.db_path), settings.data_dir)
    ensure_exp001(r)
    return r


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))
