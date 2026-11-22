"""Rotas de integração com Google Drive."""

import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse

import httpx

from ..core.auth import get_current_user
from ..core.google_drive import (
    get_auth_url,
    exchange_code,
    refresh_access_token,
    upload_folder_to_drive,
)

router = APIRouter(prefix="/api/drive", tags=["drive"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/subsidios-output"))
APP_URL = os.getenv("APP_URL", "")


async def _supabase_request(method: str, path: str, json_data: dict = None) -> dict:
    """Helper para chamadas ao Supabase com service key."""
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method,
            f"{SUPABASE_URL}/rest/v1/{path}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=json_data,
        )
        if resp.status_code >= 400:
            return {}
        try:
            return resp.json()
        except Exception:
            return {}


async def _get_valid_token(user_id: str) -> str | None:
    """Busca access token válido do usuário, renovando se necessário."""
    data = await _supabase_request(
        "GET",
        f"google_drive_tokens?user_id=eq.{user_id}&select=*",
    )
    if not data or (isinstance(data, list) and len(data) == 0):
        return None

    tokens = data[0] if isinstance(data, list) else data
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    expiry = datetime.fromisoformat(tokens["token_expiry"].replace("Z", "+00:00"))

    # Se token expira em menos de 5 min, renovar
    if expiry < datetime.now(timezone.utc) + timedelta(minutes=5):
        try:
            new_tokens = await refresh_access_token(refresh_token)
            access_token = new_tokens["access_token"]
            expires_in = new_tokens.get("expires_in", 3600)
            new_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            await _supabase_request(
                "PATCH",
                f"google_drive_tokens?user_id=eq.{user_id}",
                {
                    "access_token": access_token,
                    "token_expiry": new_expiry.isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            return None

    return access_token


@router.get("/auth")
async def drive_auth(request: Request, user: dict = Depends(get_current_user)):
    """Inicia fluxo OAuth2 do Google Drive."""
    auth_url = get_auth_url(state=user["id"])
    return JSONResponse({"auth_url": auth_url})


@router.get("/callback")
async def drive_callback(code: str, state: str = ""):
    """Callback do OAuth2. Google redireciona pra cá."""
    try:
        tokens = await exchange_code(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao trocar code: {e}")

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 3600)
    expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    user_id = state
    if not user_id:
        raise HTTPException(status_code=400, detail="State (user_id) não fornecido")

    # Upsert tokens no Supabase
    # Tentar update primeiro, se não existir, insert
    existing = await _supabase_request(
        "GET",
        f"google_drive_tokens?user_id=eq.{user_id}&select=user_id",
    )

    if existing and isinstance(existing, list) and len(existing) > 0:
        await _supabase_request(
            "PATCH",
            f"google_drive_tokens?user_id=eq.{user_id}",
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expiry": expiry.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    else:
        await _supabase_request(
            "POST",
            "google_drive_tokens",
            {
                "user_id": user_id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expiry": expiry.isoformat(),
            },
        )

    # Redirecionar de volta pro app
    redirect_url = APP_URL or "/"
    return RedirectResponse(url=f"{redirect_url}?drive=connected")


@router.get("/status")
async def drive_status(user: dict = Depends(get_current_user)):
    """Verifica se o usuário tem Drive conectado."""
    token = await _get_valid_token(user["id"])
    return {"connected": token is not None}


@router.post("/upload/{job_id}")
async def drive_upload(job_id: str, user: dict = Depends(get_current_user)):
    """Envia os arquivos organizados de um job pro Google Drive."""
    access_token = await _get_valid_token(user["id"])
    if not access_token:
        raise HTTPException(status_code=401, detail="Google Drive não conectado")

    # Encontrar a pasta de saída do job
    job_dir = OUTPUT_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado")

    # Encontrar a pasta organizada (a que não é o ZIP)
    pasta_organizada = None
    for item in job_dir.iterdir():
        if item.is_dir():
            pasta_organizada = item
            break

    if not pasta_organizada:
        raise HTTPException(status_code=404, detail="Pasta organizada não encontrada")

    try:
        folder_id = await upload_folder_to_drive(access_token, pasta_organizada)
        return {
            "success": True,
            "folder_id": folder_id,
            "drive_url": f"https://drive.google.com/drive/folders/{folder_id}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enviar pro Drive: {e}")


@router.delete("/disconnect")
async def drive_disconnect(user: dict = Depends(get_current_user)):
    """Desconecta Google Drive do usuário."""
    await _supabase_request(
        "DELETE",
        f"google_drive_tokens?user_id=eq.{user['id']}",
    )
    return {"success": True}
