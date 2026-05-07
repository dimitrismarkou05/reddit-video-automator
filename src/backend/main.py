from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.api.routes import router

app = FastAPI(
    title="Reddit Video Automator API",
    description="Orchestration layer for Reddit story -> YouTube video pipeline",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: lock to Electron origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "phase": 3}