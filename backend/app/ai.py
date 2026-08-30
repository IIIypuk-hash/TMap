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


def _client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY не задан в .env — обработка рапортов через ИИ недоступна."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _build_prompt(raw_text: str, placeholders: list[str]) -> str:
    placeholder_list = ", ".join(placeholders) if placeholders else "(шаблон не содержит полей)"
    return f"""Ты помогаешь оформлять служебные рапорты для оперативных служб на основе
свободного текста, который сотрудник написал сразу после выезда на вызов.

Исходный текст сотрудника (может быть разговорным, с сокращениями и опечатками):
---
{raw_text}
---

Сделай три вещи и верни СТРОГО один JSON-объект без пояснений и без markdown-разметки:

1. "fields" — объект с ключами ровно из этого списка: [{placeholder_list}].
   Для каждого ключа подбери значение официально-деловым языком рапорта на
   основе исходного текста. Ничего не выдумывай сверх того, что можно
   разумно вывести из текста; если данных для поля нет — оставь пустую
   строку. Не добавляй в "fields" ключи, которых нет в списке.

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
    placeholders = extract_placeholders(template_html)
    client = _client()

    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2000,
        messages=[{"role": "user", "content": _build_prompt(raw_text, placeholders)}],
    )
    raw_response = "".join(block.text for block in message.content if block.type == "text").strip()

    data = _parse_json_response(raw_response)

    fields = {k: str(v) if v is not None else "" for k, v in (data.get("fields") or {}).items()}
    # Гарантируем, что все плейсхолдеры шаблона присутствуют (пустой строкой,
    # если модель почему-то её не вернула), иначе рендер оставит {{...}}.
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
