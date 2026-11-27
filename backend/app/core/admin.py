"""Papel de ADM e acesso ao Supabase com a service key."""

import os
from datetime import datetime, timezone

import httpx
from fastapi import Depends, HTTPException

from .auth import get_current_user

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def emails_admin() -> set[str]:
    bruto = os.getenv("ADMIN_EMAILS", "mikaelcbt@gmail.com")
    return {e.strip().lower() for e in bruto.split(",") if e.strip()}


def eh_admin(user: dict) -> bool:
    return (user.get("email") or "").lower() in emails_admin()


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not eh_admin(user):
        raise HTTPException(status_code=403, detail="Só ADM pode ver isso.")
    return user


def _headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def supabase_admin_configurado() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


async def listar_usuarios() -> list[dict]:
    if not supabase_admin_configurado():
        raise HTTPException(status_code=503, detail="Falta SUPABASE_SERVICE_KEY no servidor.")
    usuarios: list[dict] = []
    async with httpx.AsyncClient(timeout=30) as client:
        pagina = 1
        while True:
            resp = await client.get(
                f"{SUPABASE_URL}/auth/v1/admin/users",
                headers=_headers(),
                params={"page": pagina, "per_page": 200},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Supabase recusou: {resp.text[:200]}")
            lote = resp.json().get("users", [])
            for u in lote:
                usuarios.append({
                    "id": u.get("id"),
                    "email": u.get("email"),
                    "nome": (u.get("user_metadata") or {}).get("nome"),
                    "criado_em": u.get("created_at"),
                    "ultimo_login": u.get("last_sign_in_at"),
                    "confirmado": bool(u.get("email_confirmed_at")),
                    "admin": (u.get("email") or "").lower() in emails_admin(),
                })
            if len(lote) < 200:
                break
            pagina += 1
    usuarios.sort(key=lambda u: u["criado_em"] or "", reverse=True)
    return usuarios


async def listar_envios(limite: int = 200) -> list[dict]:
    if not supabase_admin_configurado():
        raise HTTPException(status_code=503, detail="Falta SUPABASE_SERVICE_KEY no servidor.")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/envios_log",
            headers=_headers(),
            params={"select": "*", "order": "criado_em.desc", "limit": str(limite)},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Não consegui ler o histórico (a tabela envios_log existe?): {resp.text[:200]}",
        )
    return resp.json()


async def registrar_envio(envio_id: str, user: dict, estado: dict, total_itens: int) -> None:
    """Grava/atualiza o resumo do envio. Nunca derruba o upload se falhar."""
    if not supabase_admin_configurado():
        return
    # Só grava quando todos os arquivos já têm resultado. Assim uploads em paralelo
    # não sobrescrevem o resumo com uma contagem parcial.
    if len(estado.get("enviados") or {}) < total_itens:
        return
    destino = estado.get("destino") or {}
    enviados = estado.get("enviados") or {}
    status = [v.get("status") for v in enviados.values()]
    linha = {
        "envio_id": envio_id,
        "user_id": user.get("id") if user.get("id") != "dev" else None,
        "user_email": user.get("email"),
        "autor": destino.get("autor", ""),
        "processo": destino.get("processo", ""),
        "caminho": destino.get("caminho"),
        "url": destino.get("url"),
        "total_itens": total_itens,
        "enviados": status.count("enviado"),
        "ja_existiam": status.count("ja_existia"),
        "falhas": status.count("erro"),
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/envios_log",
                headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                json=linha,
            )
    except Exception:
        pass
