from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.cache import CacheManager
from app.api.skill_routes import router as skill_router
from app.api.skill_chain_routes import router as skill_chain_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await CacheManager.get_redis()
    except Exception:
        pass
    yield


app = FastAPI(
    title="BSC Backend API",
    version="1.0.0",
    description="Balanced Scorecard Backend Service - LLM-powered business analysis",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(skill_router)
app.include_router(skill_chain_router)


@app.get("/")
async def root():
    return {"message": "BSC Backend API is running", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
