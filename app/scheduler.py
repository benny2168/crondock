import json
import logging
import subprocess
import time
from datetime import datetime

import httpx
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import SessionLocal, Job, JobLog, Setting

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_settings(db) -> dict:
    return {s.key: s.value for s in db.query(Setting).all()}


def _substitute(text: str, settings: dict) -> str:
    """Replace {{KEY}} placeholders with values from the settings dict."""
    if not text:
        return text
    for key, value in settings.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def _format_http_body(text: str) -> str:
    """Pretty-format JSON bodies if valid JSON, otherwise return text truncated."""
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, indent=2)
    except Exception:
        return text[:4000]


# ── Executors ──────────────────────────────────────────────────────────────────

def _run_shell(command: str, settings: dict):
    cmd = _substitute(command, settings)
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300
        )
        output = (result.stdout + result.stderr).strip()
        return output, result.returncode == 0, result.returncode
    except subprocess.TimeoutExpired:
        return "Command timed out after 300s", False, -1
    except Exception as exc:
        return str(exc), False, -1


def _run_http(method: str, url: str, headers_json: str, body: str, settings: dict):
    url = _substitute(url, settings)
    headers_str = _substitute(headers_json or "{}", settings)
    body_str = _substitute(body or "", settings)

    try:
        headers = json.loads(headers_str)
    except Exception:
        headers = {}

    timeout_val = 300.0
    if "HTTP_TIMEOUT" in settings:
        try:
            timeout_val = float(settings["HTTP_TIMEOUT"])
        except ValueError:
            pass

    max_attempts = 3
    retry_delay = 10.0
    attempts_log = []

    for attempt in range(1, max_attempts + 1):
        try:
            with httpx.Client(timeout=timeout_val, verify=True) as client:
                resp = client.request(
                    method=(method or "GET").upper(),
                    url=url,
                    headers=headers,
                    content=body_str.encode() if body_str else None,
                )

            formatted_body = _format_http_body(resp.text)
            output = f"HTTP {resp.status_code}\n{formatted_body}".strip()
            is_success = 200 <= resp.status_code < 300

            # Retry on transient server error codes if attempts remain
            if resp.status_code in (502, 503, 504, 409) and attempt < max_attempts:
                attempts_log.append(
                    f"Attempt {attempt}: HTTP {resp.status_code} ({resp.text[:120].strip()}). Retrying in {int(retry_delay)}s..."
                )
                time.sleep(retry_delay)
                retry_delay *= 2
                continue

            if attempts_log:
                output = "\n".join(attempts_log) + "\n\n" + output
            return output, is_success, resp.status_code

        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
            err_msg = "Request timed out" if isinstance(exc, httpx.TimeoutException) else str(exc)
            if attempt < max_attempts:
                attempts_log.append(
                    f"Attempt {attempt}: {err_msg}. Retrying in {int(retry_delay)}s..."
                )
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                attempts_log.append(
                    f"Attempt {attempt}: {err_msg} (failed after {max_attempts} attempts)"
                )
                return "\n".join(attempts_log), False, -1
        except Exception as exc:
            return str(exc), False, -1


# ── Core job runner ────────────────────────────────────────────────────────────

def execute_job(job_id: int):
    db = SessionLocal()
    log_entry = None
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job or not job.enabled:
            return

        settings = _get_settings(db)
        log_entry = JobLog(job_id=job_id, started_at=datetime.utcnow())
        db.add(log_entry)
        db.flush()

        if job.type == "shell":
            output, success, code = _run_shell(job.command, settings)
        elif job.type == "http":
            output, success, code = _run_http(
                job.http_method, job.http_url,
                job.http_headers, job.http_body, settings
            )
        else:
            output, success, code = "Unknown job type", False, -1

        log_entry.finished_at = datetime.utcnow()
        log_entry.success = success
        log_entry.exit_code = code
        log_entry.output = output

        job.last_run_at = log_entry.started_at
        job.last_run_success = success
        job.updated_at = datetime.utcnow()

        db.commit()
        logger.info(f"Job [{job.name}] finished — success={success}, code={code}")

    except Exception as exc:
        logger.error(f"Error in job {job_id}: {exc}", exc_info=True)
        if log_entry:
            log_entry.finished_at = datetime.utcnow()
            log_entry.success = False
            log_entry.output = str(exc)
            try:
                db.commit()
            except Exception:
                pass
    finally:
        db.close()


# ── Scheduler manager ──────────────────────────────────────────────────────────

class SchedulerManager:
    def __init__(self):
        self._scheduler = BackgroundScheduler(
            executors={"default": ThreadPoolExecutor(10)},
            job_defaults={"coalesce": True, "max_instances": 1},
        )

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self):
        self._scheduler.start()
        logger.info("APScheduler started")

    def stop(self):
        self._scheduler.shutdown(wait=False)

    def load_jobs_from_db(self):
        db = SessionLocal()
        try:
            jobs = db.query(Job).filter(Job.enabled.is_(True)).all()
            for job in jobs:
                self._schedule(job.id, job.schedule)
            logger.info(f"Loaded {len(jobs)} job(s) from database")
        finally:
            db.close()

    # ── Internal scheduling ────────────────────────────────────────────────────

    def _schedule(self, job_id: int, schedule: str):
        parts = schedule.strip().split()
        if len(parts) != 5:
            logger.error(f"Bad cron expression for job {job_id}: '{schedule}'")
            return
        try:
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1],
                day=parts[2], month=parts[3], day_of_week=parts[4],
            )
            self._scheduler.add_job(
                execute_job, trigger=trigger,
                args=[job_id], id=f"job_{job_id}",
                replace_existing=True,
            )
        except Exception as exc:
            logger.error(f"Failed to schedule job {job_id}: {exc}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def enable_job(self, job_id: int, schedule: str):
        self._schedule(job_id, schedule)

    def disable_job(self, job_id: int):
        key = f"job_{job_id}"
        if self._scheduler.get_job(key):
            self._scheduler.remove_job(key)

    def remove_job(self, job_id: int):
        self.disable_job(job_id)

    def reschedule_job(self, job_id: int, schedule: str):
        self._schedule(job_id, schedule)

    def run_now(self, job_id: int):
        """Fire the job immediately in a background thread."""
        self._scheduler.add_job(
            execute_job, args=[job_id],
            id=f"run_now_{job_id}", replace_existing=True,
        )

    def get_next_run(self, job_id: int):
        apjob = self._scheduler.get_job(f"job_{job_id}")
        if apjob and apjob.next_run_time:
            return apjob.next_run_time
        return None


scheduler_manager = SchedulerManager()
