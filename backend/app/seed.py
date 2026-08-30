"""Начальные данные: создаются один раз при первом запуске, если таблицы пусты."""

from sqlalchemy.orm import Session

from .config import get_settings
from .models import ReportTemplate, Role, Unit, User
from .security import hash_password

settings = get_settings()

DEFAULT_TEMPLATE_HTML = """
<div class="report">
  <h2 style="text-align:center;">РАПОРТ</h2>
  <p style="text-align:right;">{{date}}</p>
  <p><strong>Отделение:</strong> {{unit_name}}</p>
  <p><strong>Составил:</strong> {{officer_name}}</p>
  <p><strong>Место происшествия:</strong> {{location}}</p>
  <p><strong>Категория:</strong> {{category_label}}</p>
  <p><strong>Описание обстоятельств:</strong></p>
  <p>{{description}}</p>
  <p><strong>Принятые меры:</strong></p>
  <p>{{actions_taken}}</p>
  <p style="margin-top:24px;">Подпись: ____________________ / {{officer_name}} /</p>
</div>
""".strip()


def run_seed(db: Session) -> None:
    if db.query(User).count() > 0:
        return  # уже засеяно

    default_unit = Unit(name="Отделение №1")
    db.add(default_unit)
    db.flush()

    admin = User(
        username=settings.bootstrap_admin_username,
        hashed_password=hash_password(settings.bootstrap_admin_password),
        full_name="Системный администратор",
        role=Role.admin,
        unit_id=None,
    )
    db.add(admin)
    db.flush()

    template = ReportTemplate(
        name="Стандартный рапорт",
        html_content=DEFAULT_TEMPLATE_HTML,
        is_active=True,
        updated_by_id=admin.id,
    )
    db.add(template)

    db.commit()
