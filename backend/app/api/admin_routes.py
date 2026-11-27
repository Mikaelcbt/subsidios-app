"""Rotas do painel de ADM."""

from fastapi import APIRouter, Depends

from ..core.admin import eh_admin, listar_envios, listar_usuarios, require_admin
from ..core.auth import get_current_user
from .envio_routes import drive_status

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"id": user.get("id"), "email": user.get("email"), "admin": eh_admin(user)}


@router.get("/admin/usuarios")
async def usuarios(user: dict = Depends(require_admin)):
    return {"usuarios": await listar_usuarios()}


@router.get("/admin/envios")
async def envios(user: dict = Depends(require_admin)):
    return {"envios": await listar_envios()}


@router.get("/admin/drive")
async def drive(user: dict = Depends(require_admin)):
    return await drive_status(user)
