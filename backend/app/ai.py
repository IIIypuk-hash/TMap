"""Обработка текста рапорта через Claude:
1) заполнение полей шаблона формальным языком рапорта;
2) извлечение места происшествия для геокодирования и запасных координат.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from .config import get_settings

settings = get_settings()

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# Фиксированный набор категорий — используется и для фильтрации на карте,
# и чтобы ИИ не придумывал произвольные формулировки.
CATEGORIES = [
    "atd",              # правонарушение / происшествие бытового характера
    "fire",             # пожар
    "traffic_accident",  # ДТП
    "explosion",
    "shooting",
    "drone",
    "medical",
    "other",
]

CATEGORY_LABELS = {
    "atd": "Административное/бытовое происшествие",
    "fire": "Пожар",
    "traffic_accident": "ДТП",
    "explosion": "Взрыв",
    "shooting": "Стрельба",
    "drone": "Удар БПЛА",
    "medical": "Медицинский случай",
    "other": "Иное",
}

# Поля шаблона, которые всегда подставляет код (см. reports.py), а не ИИ:
# организационные/учётные данные (кто, куда, когда), а не содержание
# рапорта. Если такое поле есть в шаблоне — оно исключается из запроса к
# модели и из ответа модели (см. process_report), чтобы ИИ не подменил
# реальные данные сотрудника своей догадкой. Список должен совпадать с
# SYSTEM_TEMPLATE_FIELDS в ops/api.js.
SYSTEM_FIELDS = [
    "date",
    "officer_name",
    "officer_rank",
    "officer_position",
    "unit_name",
    "addressee",
    "category_label",
    "location",
]

# Подсказки ИИ по смыслу конкретных полей — для более формального и
# предсказуемого результата на тех именах полей, что использует
# стандартный шаблон (см. seed.py). Поле с другим именем в кастомном
# шаблоне просто не получит подсказки — сработает общая инструкция.
FIELD_HINTS: dict[str, str] = {
    "circumstances": (
        "дата/время события, сколько сотрудников и какой техники привлекалось, "
        "что и почему делали — один связный абзац официально-деловым языком."
    ),
    "legal_basis": (
        "ссылки на постановления суда/следователя, номера уголовных/административных "
        "дел, статьи — ТОЛЬКО если это явно указано в исходном тексте; иначе пустая строка."
    ),
    "seized_items": "перечень обнаруженного и изъятого, по пунктам; пустая строка, если ничего не изымалось.",
    "persons_involved": (
        "сведения о задержанных/пострадавших/свидетелях — ФИО и статьи КоАП/УК, "
        "если названы в тексте; пустая строка, если неприменимо."
    ),
    "measures_taken": (
        "какие меры были приняты по факту произошедшего (потушено, эвакуированы, "
        "оказана помощь, применена физическая сила и т.п.)."
    ),
    "weapons_used": (
        "прямое указание, применялось ли огнестрельное оружие или спецсредства; "
        'если в тексте об этом ничего нет — напиши "Огнестрельное оружие и '
        'специальные средства не применялись".'
    ),
    "description": "связное описание произошедшего официально-деловым языком.",
    "actions_taken": "какие меры были приняты.",
}


def extract_placeholders(template_html: str) -> list[str]:
    return sorted(set(PLACEHOLDER_RE.findall(template_html)))


@dataclass
class ProcessedReport:
    fields: dict = field(default_factory=dict)
    title: str = ""
    category: str = "other"
    location_query: str = ""
    fallback_lat: Optional[float] = None
    fallback_lon: Optional[float] = None


# Для тестового режима (ai_stub_mode) — простая эвристика по ключевым
# словам вместо вызова ИИ. Не претендует на точность, только чтобы можно
# было прогнать весь путь рапорта без платного ключа.
_STUB_CATEGORY_KEYWORDS = {
    "fire": ["пожар", "возгоран", "горит", "загорел"],
    "explosion": ["взрыв", "взорв"],
    "traffic_accident": ["дтп", "авари", "столкновение", "наезд"],
    "shooting": ["стрельб", "выстрел", "огнестрел"],
    "drone": ["бпла", "дрон", "квадрокоптер"],
    "medical": ["скорая", "пострадав", "травм", "плохо себя"],
    "atd": ["дебош", "хулиган", "бытов"],
}

# Учитывает, что "г." и "ул." — сокращения с точкой, а не конец предложения
# (наивная версия принимала точку в "ул." за границу фразы и обрезала адрес).
_STUB_LOCATION_RE = re.compile(
    r"((?:г\.?|пос(?:ёлок)?\.?|село|деревня|д\.)\s*[А-ЯЁ][а-яё]+"
    r"(?:\s*(?:обл(?:асть)?\.?|край|район))?"
    r"(?:\s*,\s*(?:ул(?:ица)?\.?|пр(?:-?кт|оспект)\.?|пер(?:еулок)?\.?|"
    r"наб(?:ережная)?\.?|пл(?:ощадь)?\.?|ш(?:оссе)?\.?)\s*[А-ЯЁа-яё\-]+"
    r"(?:\s*\d+[а-яА-Я]?)?)?)"
)


def _stub_process_report(raw_text: str, template_html: str) -> "ProcessedReport":
    placeholders = extract_placeholders(template_html)
    content_placeholders = [p for p in placeholders if p not in SYSTEM_FIELDS]
    fields = {ph: "" for ph in placeholders}
    # Кладём весь текст сотрудника в наиболее содержательное поле шаблона,
    # чтобы в тестовом режиме (без ИИ) было видно хоть что-то осмысленное.
    for candidate in ("circumstances", "description"):
        if candidate in fields:
            fields[candidate] = raw_text.strip()
            break
    else:
        if content_placeholders:
            fields[content_placeholders[0]] = raw_text.strip()

    text_lower = raw_text.lower()
    category = "other"
    for cat, keywords in _STUB_CATEGORY_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            category = cat
            break

    location_match = _STUB_LOCATION_RE.search(raw_text)
    location_query = location_match.group(1).strip() if location_match else ""

    title = raw_text.strip().replace("\n", " ")
    if len(title) > 80:
        title = title[:80].rsplit(" ", 1)[0] + "…"
    title = title or "Без названия"

    return ProcessedReport(
        fields=fields,
        title=title,
        category=category,
        location_query=location_query,
        fallback_lat=None,
        fallback_lon=None,
    )


def _client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY не задан в .env — обработка рапортов через ИИ недоступна."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _build_prompt(raw_text: str, content_placeholders: list[str]) -> str:
    if content_placeholders:
        lines = []
        for p in content_placeholders:
            hint = FIELD_HINTS.get(p)
            lines.append(f'- "{p}"' + (f" — {hint}" if hint else ""))
        placeholder_list = "\n".join(lines)
    else:
        placeholder_list = "(шаблон не содержит полей, которые нужно заполнить)"
    return f"""Ты помогаешь оформлять служебные рапорты для оперативных служб на основе
свободного текста, который сотрудник написал сразу после выезда на вызов.

Исходный текст сотрудника (может быть разговорным, с сокращениями и опечатками):
---
{raw_text}
---

Сделай три вещи и верни СТРОГО один JSON-объект без пояснений и без markdown-разметки:

1. "fields" — объект с ключами ровно из этого списка (дальше — что писать в каждый):
{placeholder_list}

   Значения — официально-деловым языком рапорта, на основе исходного
   текста. Ничего не выдумывай сверх того, что можно разумно вывести из
   текста; если данных для поля нет или оно неприменимо к этому случаю —
   оставь пустую строку. Не добавляй в "fields" ключи, которых нет в списке.

2. "title" — короткий (до 80 символов) заголовок происшествия для списка на карте.

3. "category" — одна из строк: {", ".join(CATEGORIES)} (выбери наиболее подходящую).

4. "location_query" — адрес или описание места происшествия одной строкой,
   пригодное для геокодирования (например: "г. Москва, ул. Ленина, 10" или
   "пос. Ивановка, Тверская область"). Если из текста место не определяется
   однозначно — оставь пустую строку.

5. "fallback_lat" и "fallback_lon" — приблизительные координаты места (числа
   с плавающей точкой) как запасной вариант, если геокодирование по
   location_query не даст результата. Если оценить координаты невозможно —
   верни null для обоих.

Ответ — только JSON, ничего больше. Пример структуры:
{{"fields": {{"...": "..."}}, "title": "...", "category": "...", "location_query": "...", "fallback_lat": null, "fallback_lon": null}}
"""


def process_report(raw_text: str, template_html: str) -> ProcessedReport:
    if settings.ai_stub_mode:
        return _stub_process_report(raw_text, template_html)

    placeholders = extract_placeholders(template_html)
    # Системные поля (дата, ФИО/звание сотрудника, отделение, адресат и
    # т.п.) код подставляет сам после этого вызова (см. reports.py) — не
    # спрашиваем их у модели и не доверяем её ответу по ним, даже если она
    # его всё равно пришлёт.
    content_placeholders = [p for p in placeholders if p not in SYSTEM_FIELDS]
    client = _client()

    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2000,
        messages=[{"role": "user", "content": _build_prompt(raw_text, content_placeholders)}],
    )
    raw_response = "".join(block.text for block in message.content if block.type == "text").strip()

    data = _parse_json_response(raw_response)

    fields = {
        k: str(v) if v is not None else ""
        for k, v in (data.get("fields") or {}).items()
        if k in content_placeholders
    }
    # Гарантируем, что все плейсхолдеры шаблона присутствуют (пустой строкой,
    # если модель почему-то её не вернула), иначе рендер оставит {{...}}.
    # Системные поля тоже получают пустую заглушку здесь — реальные значения
    # подставит reports.py уже после этого вызова.
    for ph in placeholders:
        fields.setdefault(ph, "")

    category = str(data.get("category") or "other")
    if category not in CATEGORIES:
        category = "other"

    return ProcessedReport(
        fields=fields,
        title=str(data.get("title") or "")[:300] or "Без названия",
        category=category,
        location_query=str(data.get("location_query") or ""),
        fallback_lat=_safe_float(data.get("fallback_lat")),
        fallback_lon=_safe_float(data.get("fallback_lon")),
    )


def _safe_float(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_json_response(text: str) -> dict:
    # Модель обычно возвращает чистый JSON, но на случай markdown-обёртки
    # (```json ... ```) вырезаем содержимое между первой { и последней }.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"ИИ вернул ответ, который не удалось разобрать как JSON: {text[:500]}")


def render_template(template_html: str, fields: dict) -> str:
    """Подставляет значения полей в HTML-шаблон, экранируя пользовательский
    текст, чтобы он не мог сломать разметку или внедрить скрипт."""

    import html as html_module

    def replace(match: re.Match) -> str:
        key = match.group(1)
        value = fields.get(key, "")
        escaped = html_module.escape(value).replace("\n", "<br>")
        return escaped

    return PLACEHOLDER_RE.sub(replace, template_html)
