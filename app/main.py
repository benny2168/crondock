import logging
import os
import secrets
from urllib.parse import quote
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from auth import (
    AUTH_PROVIDER, OIDC_CLIENT_ID, OIDC_REDIRECT_URI,
    clear_session, create_session, decode_jwt_payload,
    exchange_code, get_oidc_config,
    get_session, get_state_data, set_state_cookie,
)

LOGIN_PROVIDER_NAME = os.getenv("LOGIN_PROVIDER_NAME", "Synology SSO" if AUTH_PROVIDER == "synology" else "SSO")
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

# ── Public paths (no auth required) ──────────────────────────────────────────

_PUBLIC = {"/login", "/auth/start", "/auth/callback", "/auth/logout", "/api/health"}
_PUBLIC_PREFIXES = ("/static",)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public paths
        if path in _PUBLIC or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        user = get_session(request)

        if not user:
            if path.startswith("/api"):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            return RedirectResponse("/login", status_code=302)

        request.state.user = user
        return await call_next(request)


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_defaults()
    scheduler_manager.start()
    scheduler_manager.load_jobs_from_db()
    # Pre-fetch OIDC config so first login is fast
    try:
        await get_oidc_config()
    except Exception as e:
        logger.warning(f"Could not pre-fetch OIDC config: {e}")
    yield
    scheduler_manager.stop()


app = FastAPI(title="CronDock", version="1.0.0", lifespan=lifespan)
app.add_middleware(AuthMiddleware)
templates = Jinja2Templates(directory="static")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.get("/login")
async def login_page(request: Request):
    if get_session(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "provider_name": LOGIN_PROVIDER_NAME},
    )


@app.get("/auth/start")
async def auth_start():
    cfg = await get_oidc_config()
    state = secrets.token_urlsafe(32)

    params = (
        f"response_type=code"
        f"&client_id={OIDC_CLIENT_ID}"
        f"&redirect_uri={OIDC_REDIRECT_URI}"
        f"&scope=openid+email"
        f"&state={state}"
    )
    # Synology SSO requires this param to use server-side redirect flow
    # instead of its JavaScript SDK mode
    if AUTH_PROVIDER == "synology":
        params += "&synossoJSSDK=False"
    auth_url = f"{cfg['authorization_endpoint']}?{params}"

    response = RedirectResponse(auth_url, status_code=302)
    set_state_cookie(response, state)
    return response


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        logger.warning(f"OIDC error: {error}")
        return RedirectResponse("/login?error=access_denied", status_code=302)

    state_data = get_state_data(request)
    if not state_data or state_data.get("state") != state:
        logger.warning("OIDC state mismatch")
        return RedirectResponse("/login?error=state_mismatch", status_code=302)

    try:
        tokens = await exchange_code(code)
    except Exception as e:
        detail = quote(str(e)[:120], safe='')
        logger.error(f"Token exchange failed [{type(e).__name__}]: {e!r}")
        return RedirectResponse(f"/login?error=token_exchange&detail={detail}", status_code=302)

    id_token = tokens.get("id_token", "")
    user = decode_jwt_payload(id_token)

    if not user:
        return RedirectResponse("/login?error=invalid_token", status_code=302)

    logger.info(f"User logged in: {user.get('username') or user.get('email')}")
    response = RedirectResponse("/", status_code=302)
    # Clear state cookie
    response.delete_cookie("crondock_oidc_state")
    create_session(response, user)
    return response


@app.get("/auth/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    clear_session(response)
    return response


@app.get("/api/me")
async def me(request: Request):
    user = get_session(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


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
    return (
        db.query(JobLog)
        .filter(JobLog.job_id == job_id)
        .order_by(JobLog.started_at.desc())
        .limit(limit)
        .all()
    )


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
async def root(request: Request):
    return FileResponse("static/index.html")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    return FileResponse("static/index.html")
