"""AMAS Control Center - FastAPI app factory.

Run:  uvicorn app.main:app --reload   (or: amas serve)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import Settings, get_settings
from app.storage.db import Database
from app.storage.repository import Repository
from app.taste_engine.profiles import ensure_exp001

WEB_DIR = Path(__file__).parent / "web"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_dirs()
    app = FastAPI(title="AMAS Control Center", version="0.1.0")
    db = Database(settings.db_path)
    app.state.settings = settings
    app.state.repo = Repository(db, settings.data_dir)
    ensure_exp001(app.state.repo)  # EXP-001 is available immediately

    app.include_router(router)
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html")

    return app


def __getattr__(name: str):  # lazy `app` so importing the module in tests doesn't touch ./data
    if name == "app":
        global app
        app = create_app()
        return app
    raise AttributeError(name)
