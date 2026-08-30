"""Правила видимости/редактирования дел по уровню допуска.

- employee (сотрудник): видит и дополняет только дела, которые создал сам.
- commander (командир отделения): видит и дополняет все дела своего отделения.
- staff (штаб) / admin (сисадмин): видят и дополняют все дела всех отделений.
"""

from .models import Case, Role, User


def can_access_case(user: User, case: Case) -> bool:
    if user.role in (Role.staff, Role.admin):
        return True
    if user.role == Role.commander:
        return case.unit_id == user.unit_id
    if user.role == Role.employee:
        return case.created_by_id == user.id
    return False
