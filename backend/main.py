from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.api.routes import router
from backend.api.sse import sse_router

app = FastAPI(
    title="Reddit Video Automator API",
    description="Orchestration layer for Reddit story -> YouTube video pipeline",
    version="0.4.0",
)

# Lock CORS to Electron origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "app://rva"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(router, prefix="/api/v1")
app.include_router(sse_router, prefix="/api/v1")

@app.get("/health")
def health():
    return {"status": "ok", "phase": 4, "sse": True}
