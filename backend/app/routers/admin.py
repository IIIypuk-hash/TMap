from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ReportTemplate, Role, Unit, User
from ..schemas import (
    TemplateOut,
    TemplateUpdate,
    UnitCreate,
    UnitOut,
    UnitUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from ..security import hash_password, require_roles

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles(Role.admin))])


# ---------- Шаблон рапорта ----------

@router.get("/template", response_model=TemplateOut)
def get_active_template(db: Session = Depends(get_db)):
    template = db.query(ReportTemplate).filter(ReportTemplate.is_active.is_(True)).first()
    if template is None:
        raise HTTPException(status_code=404, detail="Активный шаблон не найден")
    return template


@router.put("/template", response_model=TemplateOut)
def update_active_template(
    payload: TemplateUpdate,
    current_user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    if "{{" not in payload.html_content:
        raise HTTPException(
            status_code=400,
            detail="Шаблон не содержит ни одного поля вида {{имя_поля}}",
        )
    template = db.query(ReportTemplate).filter(ReportTemplate.is_active.is_(True)).first()
    if template is None:
        template = ReportTemplate(is_active=True)
        db.add(template)
    template.name = payload.name
    template.html_content = payload.html_content
    template.updated_by_id = current_user.id
    db.commit()
    db.refresh(template)
    return template


# ---------- Отделения ----------

@router.get("/units", response_model=list[UnitOut])
def list_units(db: Session = Depends(get_db)):
    return db.query(Unit).order_by(Unit.name).all()


@router.post("/units", response_model=UnitOut, status_code=201)
def create_unit(payload: UnitCreate, db: Session = Depends(get_db)):
    if db.query(Unit).filter(Unit.name == payload.name).first():
        raise HTTPException(status_code=400, detail="Отделение с таким названием уже существует")
    unit = Unit(name=payload.name, report_addressee=payload.report_addressee)
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


@router.put("/units/{unit_id}", response_model=UnitOut)
def update_unit(unit_id: int, payload: UnitUpdate, db: Session = Depends(get_db)):
    unit = db.query(Unit).filter(Unit.id == unit_id).first()
    if unit is None:
        raise HTTPException(status_code=404, detail="Отделение не найдено")
    if db.query(Unit).filter(Unit.name == payload.name, Unit.id != unit_id).first():
        raise HTTPException(status_code=400, detail="Отделение с таким названием уже существует")
    unit.name = payload.name
    unit.report_addressee = payload.report_addressee
    db.commit()
    db.refresh(unit)
    return unit


# ---------- Пользователи ----------

@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.username).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")
    if payload.role != Role.admin and payload.unit_id is None:
        raise HTTPException(status_code=400, detail="Для этой роли нужно указать отделение")
    if payload.unit_id is not None and not db.query(Unit).filter(Unit.id == payload.unit_id).first():
        raise HTTPException(status_code=404, detail="Отделение не найдено")

    user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        rank=payload.rank,
        position=payload.position,
        role=payload.role,
        unit_id=payload.unit_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if payload.role != Role.admin and payload.unit_id is None:
        raise HTTPException(status_code=400, detail="Для этой роли нужно указать отделение")
    if payload.unit_id is not None and not db.query(Unit).filter(Unit.id == payload.unit_id).first():
        raise HTTPException(status_code=404, detail="Отделение не найдено")

    user.full_name = payload.full_name
    user.rank = payload.rank
    user.position = payload.position
    user.role = payload.role
    user.unit_id = payload.unit_id
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user
