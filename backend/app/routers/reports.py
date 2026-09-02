from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..ai import CATEGORIES, CATEGORY_LABELS, process_report, render_template
from ..database import get_db
from ..geocode import geocode
from ..models import Case, Document, ReportTemplate, Role, User
from ..permissions import can_access_case
from ..schemas import CaseDetail, ReportConfirmRequest, ReportDraft, ReportPreviewRequest
from ..security import require_min_role
from ..serializers import case_to_detail

router = APIRouter(prefix="/reports", tags=["reports"])


def _check_case_access(db: Session, current_user: User, case_id: Optional[int]) -> Optional[Case]:
    if case_id is None:
        return None
    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    if not can_access_case(current_user, case):
        raise HTTPException(status_code=403, detail="Нет доступа к этому делу")
    return case


def _resolve_location(processed) -> tuple[Optional[float], Optional[float], bool]:
    lat, lon = None, None
    needs_manual = True
    coords = geocode(processed.location_query)
    if coords:
        lat, lon = coords
        needs_manual = False
    elif processed.fallback_lat is not None and processed.fallback_lon is not None:
        lat, lon = processed.fallback_lat, processed.fallback_lon
        needs_manual = True  # координата приблизительная от ИИ — стоит перепроверить
    return lat, lon, needs_manual


def _system_fields(current_user: User, category: str, location_query: str) -> dict:
    """Организационные поля, которые ВСЕГДА берутся из БД/кода, а не из ИИ
    и не из того, что мог прислать клиент — иначе в подписанном документе
    можно подменить, кто и от чьего имени докладывает. Прямое присваивание
    (не setdefault!): даже если ключ уже есть в fields пустой строкой
    (плейсхолдер шаблона без значения от ИИ), значение должно замениться."""

    unit = current_user.unit
    return {
        "officer_name": current_user.full_name or current_user.username,
        "officer_rank": current_user.rank,
        "officer_position": current_user.position,
        "unit_name": unit.name if unit else "",
        "addressee": unit.report_addressee if unit else "",
        "category_label": CATEGORY_LABELS.get(category, category),
        "location": location_query,
    }


@router.post("/preview", response_model=ReportDraft)
def preview_report(
    payload: ReportPreviewRequest,
    current_user: User = Depends(require_min_role(Role.employee)),
    db: Session = Depends(get_db),
):
    """Шаг 1: прогоняет текст сотрудника через ИИ и возвращает черновик —
    ничего не сохраняет в БД. Сотрудник правит поля/категорию/точку на карте
    и подтверждает через /reports/confirm."""

    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="Текст рапорта не может быть пустым")

    _check_case_access(db, current_user, payload.case_id)

    template = db.query(ReportTemplate).filter(ReportTemplate.is_active.is_(True)).first()
    if template is None:
        raise HTTPException(
            status_code=500,
            detail="Активный шаблон рапорта не настроен — обратитесь к сисадмину",
        )

    try:
        processed = process_report(payload.text, template.html_content)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Автоподставляемые системные поля — доступны в шаблоне наравне с теми,
    # что заполнил ИИ, но задаются кодом, а не моделью (дата, отделение,
    # автор, адресат и т.п.).
    processed.fields["date"] = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
    processed.fields.update(_system_fields(current_user, processed.category, processed.location_query))

    lat, lon, needs_manual = _resolve_location(processed)
    rendered_html = render_template(template.html_content, processed.fields)

    return ReportDraft(
        template_id=template.id,
        template_html=template.html_content,
        raw_text=payload.text,
        fields=processed.fields,
        title=processed.title,
        category=processed.category,
        category_label=CATEGORY_LABELS.get(processed.category, processed.category),
        location_text=processed.location_query,
        lat=lat,
        lon=lon,
        needs_manual_location=needs_manual,
        rendered_html=rendered_html,
        case_id=payload.case_id,
    )


@router.post("", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
def confirm_report(
    payload: ReportConfirmRequest,
    current_user: User = Depends(require_min_role(Role.employee)),
    db: Session = Depends(get_db),
):
    """Шаг 2: сохраняет черновик (возможно, отредактированный сотрудником —
    поля, категория, точка на карте) как дело/документ."""

    if not payload.fields:
        raise HTTPException(status_code=400, detail="Нет данных для оформления рапорта")

    template = db.query(ReportTemplate).filter(ReportTemplate.id == payload.template_id).first()
    if template is None:
        raise HTTPException(
            status_code=400,
            detail="Шаблон, использованный при формировании рапорта, больше не существует — сформируйте рапорт заново",
        )

    category = payload.category if payload.category in CATEGORIES else "other"
    # Организационные поля пере-подставляем из БД на момент сохранения, а
    # не берём из payload.fields как есть: черновик мог редактироваться в
    # браузере, и без этого в подписанном документе можно было бы
    # подделать, кто и от чьего имени докладывает.
    fields = dict(payload.fields)
    fields["date"] = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
    fields.update(_system_fields(current_user, category, payload.location_text))
    rendered_html = render_template(template.html_content, fields)

    case = _check_case_access(db, current_user, payload.case_id)

    if case is None:
        if current_user.unit_id is None:
            raise HTTPException(
                status_code=400,
                detail="У вас не назначено отделение — обратитесь к сисадмину",
            )
        case = Case(
            unit_id=current_user.unit_id,
            created_by_id=current_user.id,
            title=(payload.title or "Без названия")[:300],
            category=category,
            lat=payload.lat,
            lon=payload.lon,
            location_text=payload.location_text,
            needs_manual_location=payload.needs_manual_location,
        )
        db.add(case)
        db.flush()
    else:
        # Дополняем существующее дело: координаты/категорию не перезаписываем
        # автоматически, чтобы не "прыгала" точка, уже проверенная штабом.
        if case.lat is None and payload.lat is not None:
            case.lat, case.lon = payload.lat, payload.lon
            case.needs_manual_location = payload.needs_manual_location

    document = Document(
        case_id=case.id,
        author_id=current_user.id,
        template_id=template.id,
        raw_text=payload.raw_text,
        rendered_html=rendered_html,
    )
    db.add(document)
    db.commit()
    db.refresh(case)

    return case_to_detail(case)
