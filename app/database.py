from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    DateTime, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import os

DATA_DIR = os.getenv("DATA_DIR", "/data")
DATABASE_URL = f"sqlite:///{DATA_DIR}/crondock.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    description = Column(String(500))
    is_secret = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(500))
    type = Column(String(50), nullable=False)   # shell | http
    schedule = Column(String(100), nullable=False)
    enabled = Column(Boolean, default=True)
    # Shell
    command = Column(Text)
    # HTTP
    http_method = Column(String(10))
    http_url = Column(Text)
    http_headers = Column(Text)   # JSON string
    http_body = Column(Text)
    # Status
    last_run_at = Column(DateTime)
    last_run_success = Column(Boolean)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    logs = relationship(
        "JobLog", back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobLog.started_at.desc()"
    )


class JobLog(Base):
    __tablename__ = "job_logs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    success = Column(Boolean)
    exit_code = Column(Integer)
    output = Column(Text)

    job = relationship("Job", back_populates="logs")

    @property
    def duration_ms(self):
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds() * 1000)
        return None


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def seed_defaults():
    db = SessionLocal()
    try:
        # ── Global settings ──────────────────────────────────────────────
        defaults = [
            ("ABRAHAM_PORTAINER_URL",         "https://docker.abraham16.com",                         "Abraham Portainer base URL",          False),
            ("ABRAHAM_PORTAINER_TOKEN",        "ptr_LAYVFvw5+DscmC2s2QsM+5aeO6iXGYcR4+KwjH7f/eU=",  "Abraham Portainer API token",          True),
            ("ABRAHAM_PORTAINER_ENDPOINT_ID",  "5",                                                    "Abraham Synology Docker endpoint ID", False),
            ("MTCD_PORTAINER_URL",             "https://docker.server.mtcd.org",                       "MTCD Portainer base URL",             False),
            ("MTCD_PORTAINER_TOKEN",           "ptr_caKh16OVXC+3G4shu9s7TXtumDZY04R6wwaOYkq+Pls=",  "MTCD Portainer API token",             True),
            ("MTCD_PORTAINER_ENDPOINT_ID",     "2",                                                    "MTCD Synology Docker endpoint ID",    False),
        ]
        for key, value, desc, secret in defaults:
            if not db.query(Setting).filter(Setting.key == key).first():
                db.add(Setting(key=key, value=value, description=desc, is_secret=secret))

        # ── Default jobs ─────────────────────────────────────────────────
        if db.query(Job).count() == 0:
            db.add(Job(
                name="Docker Cleanup — Abraham",
                description="Remove unused Docker images from Abraham Synology NAS via Portainer API",
                type="http",
                schedule="30 3 * * *",
                enabled=True,
                http_method="POST",
                http_url=(
                    "{{ABRAHAM_PORTAINER_URL}}/api/endpoints/{{ABRAHAM_PORTAINER_ENDPOINT_ID}}"
                    "/docker/images/prune?filters=%7B%22dangling%22%3A%5B%22false%22%5D%7D"
                ),
                http_headers='{"X-API-Key": "{{ABRAHAM_PORTAINER_TOKEN}}"}',
                http_body=None,
            ))
            db.add(Job(
                name="Docker Cleanup — MTCD",
                description="Remove unused Docker images from MTCD Synology NAS via Portainer API",
                type="http",
                schedule="0 3 * * *",
                enabled=True,
                http_method="POST",
                http_url=(
                    "{{MTCD_PORTAINER_URL}}/api/endpoints/{{MTCD_PORTAINER_ENDPOINT_ID}}"
                    "/docker/images/prune?filters=%7B%22dangling%22%3A%5B%22false%22%5D%7D"
                ),
                http_headers='{"X-API-Key": "{{MTCD_PORTAINER_TOKEN}}"}',
                http_body=None,
            ))

        db.commit()
    finally:
        db.close()
