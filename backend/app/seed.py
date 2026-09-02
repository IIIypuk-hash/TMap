"""Начальные данные: создаются один раз при первом запуске, если таблицы пусты."""

from sqlalchemy.orm import Session

from .config import get_settings
from .models import ReportTemplate, Role, Unit, User
from .security import hash_password

settings = get_settings()

DEFAULT_TEMPLATE_HTML = """
<div class="report">
  <p style="text-align:right; white-space:pre-line;">{{addressee}}</p>

  <h2 style="text-align:center; margin-top:28px;">РАПОРТ</h2>
  <p style="text-align:right;">{{date}}</p>

  <p>Докладываю Вам, что {{circumstances}}</p>

  <p>{{legal_basis}}</p>

  <p><strong>Обнаружено и изъято:</strong> {{seized_items}}</p>

  <p><strong>Сведения о задержанных/пострадавших:</strong> {{persons_involved}}</p>

  <p><strong>Принятые меры:</strong> {{measures_taken}}</p>

  <p>{{weapons_used}}</p>

  <table style="width:100%; margin-top:32px; border:none; border-collapse:collapse;">
    <tr>
      <td style="border:none; padding:0; vertical-align:bottom;">
        {{officer_position}}<br>
        {{unit_name}}<br>
        {{officer_rank}}
      </td>
      <td style="border:none; padding:0; text-align:right; vertical-align:bottom;">
        {{officer_name}}
      </td>
    </tr>
  </table>
</div>
""".strip()

# Заготовка "шапки" по умолчанию для отделения — сисадмин правит под
# реального адресата (см. admin.html, PUT /admin/units/{id}).
DEFAULT_UNIT_ADDRESSEE = "Командиру [название подразделения]\n[звание] [Фамилия И.О.]"


def run_seed(db: Session) -> None:
    if db.query(User).count() > 0:
        return  # уже засеяно

    default_unit = Unit(name="Отделение №1", report_addressee=DEFAULT_UNIT_ADDRESSEE)
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
