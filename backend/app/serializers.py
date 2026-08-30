from .models import Case
from .schemas import CaseDetail, CaseListItem, DocumentOut


def case_to_list_item(case: Case) -> CaseListItem:
    return CaseListItem(
        id=case.id,
        title=case.title,
        category=case.category,
        status=case.status,
        lat=case.lat,
        lon=case.lon,
        needs_manual_location=case.needs_manual_location,
        unit_id=case.unit_id,
        unit_name=case.unit.name,
        created_at=case.created_at,
        document_count=len(case.documents),
    )


def case_to_detail(case: Case) -> CaseDetail:
    return CaseDetail(
        id=case.id,
        title=case.title,
        category=case.category,
        status=case.status,
        lat=case.lat,
        lon=case.lon,
        needs_manual_location=case.needs_manual_location,
        unit_id=case.unit_id,
        unit_name=case.unit.name,
        created_at=case.created_at,
        document_count=len(case.documents),
        location_text=case.location_text,
        created_by_id=case.created_by_id,
        created_by_name=case.created_by.full_name or case.created_by.username,
        documents=[
            DocumentOut(
                id=d.id,
                case_id=d.case_id,
                author_id=d.author_id,
                author_name=d.author.full_name or d.author.username,
                raw_text=d.raw_text,
                rendered_html=d.rendered_html,
                created_at=d.created_at,
            )
            for d in case.documents
        ],
    )
