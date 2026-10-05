import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from backend.config import settings
from backend.database.connection import Base, SessionLocal, engine
from backend.database import models  # Register metadata before create_all.
from backend.routers import admin, alerts, auth, chatbot, donations, incidents, relief, shelters, teams, users
from backend.seed import seed_demo
from backend.database.migrations import backfill_domain_records, migrate_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate_schema(engine)
    with SessionLocal() as db:
        if settings.demo_mode:
            seed_demo(db)
        backfill_domain_records(db)
        db.commit()
    # Persisted pending rows are resumable work; startup does not discard them.
    pending_ids = []
    with SessionLocal() as db:
        pending_ids = [analysis.incident_id for analysis in db.scalars(select(models.ReportAnalysis))
                       if analysis.result.get("analysis_status") == "pending"]
    tasks = [asyncio.create_task(incidents.process_incident(incident_id)) for incident_id in pending_ids]
    yield
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="ResQ Kerala", version="2.0.0", description="AI-assisted flood response MVP with human verification and local Ollama agents.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])
for router in (auth.router, users.router, incidents.router, teams.router, shelters.router, relief.router, alerts.router, donations.router, admin.router, chatbot.router):
    app.include_router(router)


@app.get("/health", tags=["System"])
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database = True
    except Exception:
        database = False
    return {"status": "ok" if database else "degraded", "database": database, "demo_mode": settings.demo_mode,
            "ai": {"provider": "ollama", "model": settings.ollama_model, "enabled": settings.ai_enabled, "status": "configured" if settings.ai_enabled else "disabled"}}


@app.get("/", include_in_schema=False)
def index():
    return {"name": "ResQ Kerala API", "docs": "/docs", "health": "/health", "frontend": "http://localhost:5173"}
