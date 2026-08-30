from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, SessionLocal, engine
from .routers import admin, auth, cases, reports
from .seed import run_seed

settings = get_settings()

Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    run_seed(db)

app = FastAPI(title="TMap — внутренние рапорты", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # Плюс любые проброшенные порты GitHub Codespaces — чтобы можно было
    # тестировать без постоянного хостинга (см. .devcontainer/). На боевом
    # стенде эту строку стоит убрать или сузить до конкретного домена.
    allow_origin_regex=r"https://.*\.app\.github\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(reports.router)
app.include_router(cases.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
