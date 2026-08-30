from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Case, Role, User
from ..permissions import can_access_case
from ..schemas import CaseDetail, CaseListItem, CaseLocationUpdate, CaseStatusUpdate
from ..security import get_current_user, require_min_role
from ..serializers import case_to_detail, case_to_list_item

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=list[CaseListItem])
def list_cases(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Case)
    if current_user.role in (Role.staff, Role.admin):
        pass  # видят все дела
    elif current_user.role == Role.commander:
        query = query.filter(Case.unit_id == current_user.unit_id)
    else:  # employee
        query = query.filter(Case.created_by_id == current_user.id)

    cases = query.order_by(Case.created_at.desc()).all()
    return [case_to_list_item(c) for c in cases]


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    if not can_access_case(current_user, case):
        raise HTTPException(status_code=403, detail="Нет доступа к этому делу")
    return case_to_detail(case)


@router.put("/{case_id}/location", response_model=CaseDetail)
def update_location(
    case_id: int,
    payload: CaseLocationUpdate,
    # Ручную корректировку точки разрешаем командиру (своё отделение) и выше —
    # рядовой сотрудник координаты дела не двигает.
    current_user: User = Depends(require_min_role(Role.commander)),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    if not can_access_case(current_user, case):
        raise HTTPException(status_code=403, detail="Нет доступа к этому делу")
    case.lat = payload.lat
    case.lon = payload.lon
    case.needs_manual_location = False
    db.commit()
    db.refresh(case)
    return case_to_detail(case)


@router.put("/{case_id}/status", response_model=CaseDetail)
def update_status(
    case_id: int,
    payload: CaseStatusUpdate,
    current_user: User = Depends(require_min_role(Role.commander)),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    if not can_access_case(current_user, case):
        raise HTTPException(status_code=403, detail="Нет доступа к этому делу")
    case.status = payload.status
    db.commit()
    db.refresh(case)
    return case_to_detail(case)
