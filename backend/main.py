from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from api.routes import router
from api.sse import router as sse_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    yield
    # Shutdown (if needed)
    pass


app = FastAPI(
    title="Reddit Video Automator API",
    description="Orchestration layer for Reddit story -> YouTube video pipeline",
    version="0.4.0",
    lifespan=lifespan,
)

# Lock CORS to Electron origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "app://rva"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(sse_router, prefix="/api/v1")

@app.get("/")
def root():
    return {
        "message": "Reddit Video Automator API",
        "version": "0.4.0",
        "docs": "/docs",
        "health": "/health",
    }

@app.get("/health")
def health():
    return {"status": "ok", "phase": 4, "sse": True}