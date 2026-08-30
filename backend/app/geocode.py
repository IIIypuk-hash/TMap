"""Геокодинг через публичный Nominatim (OpenStreetMap) — тот же провайдер
тайлов, что уже используется картой на фронтенде."""

from typing import Optional

import httpx

from .config import get_settings

settings = get_settings()

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def geocode(query: str) -> Optional[tuple[float, float]]:
    """Возвращает (lat, lon) для текстового описания места, ограничиваясь
    Россией. None, если ничего не найдено или произошла ошибка сети —
    вызывающий код должен предусмотреть резервный вариант (ручная расстановка
    точки или запасные координаты от ИИ)."""

    if not query or not query.strip():
        return None

    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "ru",
            },
            headers={"User-Agent": settings.nominatim_user_agent},
            timeout=10.0,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        lat = float(results[0]["lat"])
        lon = float(results[0]["lon"])
        return lat, lon
    except (httpx.HTTPError, KeyError, ValueError, IndexError):
        return None
