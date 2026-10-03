from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.connection import check_database_connection, init_db
from app.routes import auth, buyers, dashboard, email, search

app = FastAPI(title="BuyerBridge", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://127.0.0.1:5510"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    if not check_database_connection():
        raise RuntimeError(
            "BuyerBridge could not connect to PostgreSQL. Verify DATABASE_URL, the Postgres service, and that the database is running before starting the API."
        )
    init_db()


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(search.router)
app.include_router(buyers.router)
app.include_router(email.router)
app.include_router(dashboard.router)
