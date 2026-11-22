"""Integração com Google Drive via OAuth2."""

import os
from pathlib import Path
from datetime import datetime, timezone

import httpx

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")

SCOPES = "https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"


def get_auth_url(state: str = "") -> str:
    """Gera URL de autorização do Google."""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


async def exchange_code(code: str) -> dict:
    """Troca authorization code por tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": GOOGLE_REDIRECT_URI,
        })
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Renova access token usando refresh token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        return resp.json()


async def create_folder(access_token: str, name: str, parent_id: str | None = None) -> str:
    """Cria pasta no Drive. Retorna o ID."""
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            DRIVE_FILES_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=metadata,
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def upload_file(access_token: str, file_path: Path, parent_id: str) -> str:
    """Faz upload de um arquivo pro Drive. Retorna o ID."""
    metadata = {
        "name": file_path.name,
        "parents": [parent_id],
    }

    file_content = file_path.read_bytes()

    # Multipart upload
    import json
    boundary = "subsidios_boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Type: application/json; charset=UTF-8\r\n\r\n'
        f'{json.dumps(metadata)}\r\n'
        f"--{boundary}\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_content + f"\r\n--{boundary}--".encode()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DRIVE_UPLOAD_URL}?uploadType=multipart",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            content=body,
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def upload_folder_to_drive(
    access_token: str,
    local_folder: Path,
    drive_parent_id: str | None = None,
) -> str:
    """Envia uma pasta inteira pro Drive, mantendo a estrutura."""
    # Criar pasta raiz
    root_id = await create_folder(access_token, local_folder.name, drive_parent_id)

    for item in sorted(local_folder.iterdir()):
        if item.name.startswith(".") or item.name.startswith("_"):
            continue
        if item.is_dir():
            await upload_folder_to_drive(access_token, item, root_id)
        elif item.is_file():
            await upload_file(access_token, item, root_id)

    return root_id
