from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .models import CaseStatus, Role


# ---------- Auth ----------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


# ---------- Unit ----------

class UnitCreate(BaseModel):
    name: str


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


# ---------- User ----------

class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str = ""
    role: Role
    unit_id: Optional[int] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str
    role: Role
    unit_id: Optional[int] = None
    is_active: bool


# ---------- Document ----------

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    author_id: int
    author_name: str
    raw_text: str
    rendered_html: str
    created_at: datetime


# ---------- Case ----------

class ReportPreviewRequest(BaseModel):
    text: str
    case_id: Optional[int] = None  # приложить как новый документ к существующему делу


class ReportDraft(BaseModel):
    """Черновик, сформированный ИИ — ещё не сохранён. Сотрудник правит поля
    и место на карте, затем отправляет ReportConfirmRequest."""

    template_id: int
    template_html: str  # нужен фронтенду, чтобы вживую перерисовывать превью при правке полей
    raw_text: str
    fields: dict[str, str]
    title: str
    category: str
    category_label: str
    location_text: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    needs_manual_location: bool
    rendered_html: str
    case_id: Optional[int] = None


class ReportConfirmRequest(BaseModel):
    template_id: int
    raw_text: str
    fields: dict[str, str]
    title: str
    category: str
    location_text: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    needs_manual_location: bool
    case_id: Optional[int] = None


class CaseListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    category: Optional[str] = None
    status: CaseStatus
    lat: Optional[float] = None
    lon: Optional[float] = None
    needs_manual_location: bool
    unit_id: int
    unit_name: str
    created_at: datetime
    document_count: int


class CaseDetail(CaseListItem):
    location_text: Optional[str] = None
    created_by_id: int
    created_by_name: str
    documents: list[DocumentOut]


class CaseLocationUpdate(BaseModel):
    lat: float
    lon: float


class CaseStatusUpdate(BaseModel):
    status: CaseStatus


# ---------- Report template ----------

class TemplateUpdate(BaseModel):
    name: str
    html_content: str


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    html_content: str
    is_active: bool
    updated_at: datetime
