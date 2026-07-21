import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from database import Job, JobLog, SessionLocal, Setting, init_db, seed_defaults
from models import (
    JobCreate, JobLogResponse, JobResponse, JobUpdate,
    SettingCreate, SettingResponse,
)
from scheduler import scheduler_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_defaults()
    scheduler_manager.start()
    scheduler_manager.load_jobs_from_db()
    yield
    scheduler_manager.stop()


app = FastAPI(title="CronDock", version="1.0.0", lifespan=lifespan)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Jobs ───────────────────────────────────────────────────────────────────────

@app.get("/api/jobs", response_model=List[JobResponse])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.created_at).all()
    result = []
    for job in jobs:
        jr = JobResponse.model_validate(job)
        jr.next_run_at = scheduler_manager.get_next_run(job.id)
        result.append(jr)
    return result


@app.post("/api/jobs", response_model=JobResponse, status_code=201)
def create_job(data: JobCreate, db: Session = Depends(get_db)):
    job = Job(**data.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    if job.enabled:
        scheduler_manager.enable_job(job.id, job.schedule)
    jr = JobResponse.model_validate(job)
    jr.next_run_at = scheduler_manager.get_next_run(job.id)
    return jr


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    jr = JobResponse.model_validate(job)
    jr.next_run_at = scheduler_manager.get_next_run(job.id)
    return jr


@app.put("/api/jobs/{job_id}", response_model=JobResponse)
def update_job(job_id: int, data: JobUpdate, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    job.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    if job.enabled:
        scheduler_manager.enable_job(job.id, job.schedule)
    else:
        scheduler_manager.disable_job(job.id)
    jr = JobResponse.model_validate(job)
    jr.next_run_at = scheduler_manager.get_next_run(job.id)
    return jr


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    scheduler_manager.remove_job(job_id)
    db.delete(job)
    db.commit()
    return {"ok": True}


@app.post("/api/jobs/{job_id}/run")
def run_now(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    scheduler_manager.run_now(job_id)
    return {"ok": True, "message": f"Job '{job.name}' triggered"}


@app.get("/api/jobs/{job_id}/logs", response_model=List[JobLogResponse])
def get_logs(job_id: int, limit: int = 50, db: Session = Depends(get_db)):
    logs = (
        db.query(JobLog)
        .filter(JobLog.job_id == job_id)
        .order_by(JobLog.started_at.desc())
        .limit(limit)
        .all()
    )
    return logs


# ── Settings ───────────────────────────────────────────────────────────────────

@app.get("/api/settings", response_model=List[SettingResponse])
def list_settings(db: Session = Depends(get_db)):
    return db.query(Setting).order_by(Setting.key).all()


@app.post("/api/settings", response_model=SettingResponse)
def upsert_setting(data: SettingCreate, db: Session = Depends(get_db)):
    setting = db.query(Setting).filter(Setting.key == data.key).first()
    if setting:
        for field, value in data.model_dump().items():
            setattr(setting, field, value)
        setting.updated_at = datetime.utcnow()
    else:
        setting = Setting(**data.model_dump())
        db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


@app.delete("/api/settings/{key}")
def delete_setting(key: str, db: Session = Depends(get_db)):
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        raise HTTPException(404, "Setting not found")
    db.delete(setting)
    db.commit()
    return {"ok": True}


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"ok": True, "version": "1.0.0"}


# ── Static / SPA ───────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    return FileResponse("static/index.html")
