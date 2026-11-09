"""Autenticação via Supabase JWT."""

import os
import httpx
from fastapi import HTTPException, Request

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


async def get_current_user(request: Request) -> dict:
    """Extrai e valida o usuário do token JWT do Supabase."""
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token não fornecido")

    token = auth_header.replace("Bearer ", "")

    if not SUPABASE_URL:
        # Em dev sem Supabase configurado, deixar passar
        return {"id": "dev", "email": "dev@local"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": SUPABASE_ANON_KEY,
                },
            )

        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Token inválido ou expirado")

        user_data = resp.json()
        return {
            "id": user_data.get("id"),
            "email": user_data.get("email"),
            "nome": user_data.get("user_metadata", {}).get("nome"),
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Erro ao validar token")
