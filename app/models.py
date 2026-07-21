from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class JobType(str, Enum):
    SHELL = "shell"
    HTTP = "http"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class JobBase(BaseModel):
    name: str
    description: Optional[str] = None
    type: JobType
    schedule: str
    enabled: bool = True
    command: Optional[str] = None
    http_method: Optional[HttpMethod] = None
    http_url: Optional[str] = None
    http_headers: Optional[str] = None  # JSON string
    http_body: Optional[str] = None


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    schedule: Optional[str] = None
    enabled: Optional[bool] = None
    command: Optional[str] = None
    http_method: Optional[HttpMethod] = None
    http_url: Optional[str] = None
    http_headers: Optional[str] = None
    http_body: Optional[str] = None


class JobResponse(JobBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_run_at: Optional[datetime] = None
    last_run_success: Optional[bool] = None
    next_run_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class JobLogResponse(BaseModel):
    id: int
    job_id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    success: Optional[bool] = None
    exit_code: Optional[int] = None
    output: Optional[str] = None

    model_config = {"from_attributes": True}


class SettingBase(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    is_secret: bool = False


class SettingCreate(SettingBase):
    pass


class SettingResponse(SettingBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
