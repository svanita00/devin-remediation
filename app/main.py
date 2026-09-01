"""FastAPI entrypoint for the Devin Remediation Control Plane.

Triggers (all real, reproducible — no ad-hoc scripts):
  - POST /scan        -> on-demand native Code Scan + auto-remediate + self-review
  - event Automation  -> GitHub `devin-fix` label -> remediation session -> PR
  - schedule Automation -> weekly security sweep
The two Automations are provisioned by scripts/setup_devin.py; this service runs
the on-demand pipeline and the observability control plane, and reconciles all
sessions (any origin) from the Devin API onto the dashboard.

Run:  uvicorn app.main:app   (or docker compose up)
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.config import settings
from app import store
from app.scans import trigger_scan
from app.observability import router as obs_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("control-plane")


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    store.init_db()
    log.info("Control plane starting: mode=%s target=%s", settings.devin_mode, settings.target_repo)
    if settings.devin_mode == "live" and not settings.devin_api_key:
        log.warning("DEVIN_MODE=live but DEVIN_API_KEY is empty — live calls will fail.")
    yield


app = FastAPI(title="Devin Remediation Control Plane", lifespan=lifespan)
app.include_router(obs_router)


@app.post("/scan")
async def scan(trigger: str = "manual"):
    """Kick off a native Code Scan + auto-remediation + self-review run (returns immediately)."""
    trigger_scan(trigger)
    log.info("Scan run requested (trigger=%s)", trigger)
    return {"ok": True, "status": "scan_started", "repo": settings.target_repo,
            "mode": settings.devin_mode}


@app.get("/healthz")
def healthz():
    return {"ok": True, "mode": settings.devin_mode}


@app.get("/")
def root():
    return RedirectResponse("/dashboard")
