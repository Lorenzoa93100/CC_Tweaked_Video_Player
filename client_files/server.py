"""
VBC Server — Video Block Converter for ComputerCraft: Tweaked
FastAPI-based rewrite focused on performance.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.routes import router
from api.client_routes import router as client_router
from core.config import settings
from storage.manager import storage_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure storage dirs exist
    storage_manager.init_dirs()
    print(f"[VBC] Server ready on http://0.0.0.0:{settings.PORT}")
    print(f"[VBC] Storage: {settings.STORAGE_DIR}")
    yield
    # Shutdown: nothing to clean up


app = FastAPI(
    title="VBC Server",
    description="Video Block Converter for ComputerCraft: Tweaked",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(client_router)
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=False,
        workers=1,  # 1 worker: FFmpeg est déjà multi-threadé
    )
