import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


class Role(str, enum.Enum):
    # Уровни допуска, от низшего к высшему.
    employee = "employee"      # сотрудник, выезжающий на вызов — подаёт рапорты
    commander = "commander"    # командир отделения — видит точки своего отделения
    staff = "staff"            # штаб — видит все точки всех отделений
    admin = "admin"            # сисадмин — управляет шаблоном рапорта, пользователями, отделениями


class CaseStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class Unit(Base):
    """Отделение."""

    __tablename__ = "units"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="unit")
    cases = relationship("Case", back_populates="unit")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=False, default="")
    role = Column(Enum(Role), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    unit = relationship("Unit", back_populates="users")
    cases_created = relationship("Case", back_populates="created_by")
    documents_authored = relationship("Document", back_populates="author")


class Case(Base):
    """Дело/происшествие. Создаётся из первого рапорта, дальше может
    накапливать несколько документов (Document)."""

    __tablename__ = "cases"

    id = Column(Integer, primary_key=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    title = Column(String(300), nullable=False)
    category = Column(String(100), nullable=True)
    status = Column(Enum(CaseStatus), default=CaseStatus.open, nullable=False)

    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    location_text = Column(String(500), nullable=True)
    # Координаты не удалось определить автоматически — точку нужно
    # разместить/поправить вручную (штаб/командир).
    needs_manual_location = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    unit = relationship("Unit", back_populates="cases")
    created_by = relationship("User", back_populates="cases_created")
    documents = relationship(
        "Document", back_populates="case", order_by="Document.created_at", cascade="all, delete-orphan"
    )


class Document(Base):
    """Один документ (рапорт) в деле. По одному делу их может быть несколько."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("report_templates.id"), nullable=True)

    raw_text = Column(Text, nullable=False)       # исходный текст сотрудника
    rendered_html = Column(Text, nullable=False)  # итоговый рапорт по шаблону

    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="documents")
    author = relationship("User", back_populates="documents_authored")
    template = relationship("ReportTemplate")


class ReportTemplate(Base):
    """Шаблон рапорта. Активен только один — его редактирует сисадмин."""

    __tablename__ = "report_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    html_content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
