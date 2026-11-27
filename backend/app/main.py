"""FastAPI application."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .api.drive_routes import router as drive_router
from .api.envio_routes import router as envio_router
from .api.admin_routes import router as admin_router

app = FastAPI(
    title="Subsídios Processuais",
    description="Automação de organização e conferência de subsídios",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes primeiro
app.include_router(router)
app.include_router(drive_router)
app.include_router(envio_router)
app.include_router(admin_router)

# Servir frontend estático (build do React)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    from fastapi.responses import FileResponse

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        file_path = static_dir / path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(static_dir / "index.html")
