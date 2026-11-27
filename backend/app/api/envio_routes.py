"""Rotas do envio de subsídios pro Drive do escritório.

Fluxo da tela:
    POST   /api/envios                                  cria um envio vazio
    POST   /api/envios/{id}/documentos                  documentos e ZIPs (extrai tudo)
    DELETE /api/envios/{id}/documentos/{doc_id}
    POST   /api/envios/{id}/documentos/mover-faturas    documentos que são fatura vão pra área de faturas
    POST   /api/envios/{id}/faturas                     faturas (PDF ou ZIP), junta num PDF só
    DELETE /api/envios/{id}/faturas/{fatura_id}
    POST   /api/envios/{id}/faturas/ordem               muda a ordem (data, nome ou manual)
    GET    /api/envios/{id}/faturas.pdf                 baixa/visualiza o PDF juntado
    GET    /api/envios/destino?autor=&processo=         mostra onde vai salvar (não cria nada)
    POST   /api/envios/{id}/pasta                       cria pasta do processo e SUBSÍDIOS (ou reusa)
    POST   /api/envios/{id}/itens/{item_id}/subir       sobe um arquivo (o front chama um por um)
    GET    /api/envios/drive/status                     conexão do Drive do escritório
"""

import asyncio
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.admin import registrar_envio
from ..core.auth import get_current_user
from ..core import drive_escritorio
from ..core.drive_escritorio import DriveEscritorio, DriveErro, modo_configurado
from ..core.envio import Envio, EnvioErro

router = APIRouter(prefix="/api/envios", tags=["envios"])

# Evita que dois uploads do mesmo envio criem a pasta do processo duas vezes
_locks_pasta: dict[str, asyncio.Lock] = {}


class Ordem(BaseModel):
    modo: str
    ids: list[str] | None = None


class Ids(BaseModel):
    ids: list[str]


class DadosProcesso(BaseModel):
    autor: str
    processo: str


def _abrir(envio_id: str, user: dict) -> Envio:
    try:
        return Envio.abrir(envio_id, user["id"])
    except EnvioErro as e:
        raise HTTPException(status_code=404, detail=str(e))


async def _receber(arquivos: list[UploadFile]) -> Path:
    pasta = Path(tempfile.mkdtemp(prefix="envio-in-"))
    for arq in arquivos:
        nome = Path(arq.filename or "arquivo").name or "arquivo"
        destino = pasta / nome
        n = 1
        while destino.exists():
            destino = pasta / f"{Path(nome).stem}_{n}{Path(nome).suffix}"
            n += 1
        with open(destino, "wb") as f:
            shutil.copyfileobj(arq.file, f)
    return pasta


# ---------------------------------------------------------------------------
# Status do Drive
# ---------------------------------------------------------------------------

@router.get("/drive/status")
async def drive_status(user: dict = Depends(get_current_user)):
    modo = modo_configurado()
    if not modo:
        return {"configurado": False, "modo": None, "faixas": [], "erro": None}
    try:
        async with DriveEscritorio() as drive:
            faixas = await drive.faixas(usar_cache=False)
            return {
                "configurado": True,
                "modo": modo,
                "conta": drive.email,
                "teste": bool(drive_escritorio.RAIZ_TESTE_ID),
                "faixas": [{"nome": f.nome, "de": f.de, "ate": f.ate} for f in faixas],
                "erro": None if faixas else "A conta do app não participa de nenhum Drive de faixa (ex.: CÍVEL- Pan A - C).",
            }
    except DriveErro as e:
        return {"configurado": True, "modo": modo, "faixas": [], "erro": str(e)}


@router.get("/destino")
async def destino(autor: str, processo: str, user: dict = Depends(get_current_user)):
    try:
        async with DriveEscritorio() as drive:
            d = await drive.resolver_destino(autor, processo)
            return d.para_dict()
    except DriveErro as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Preparo
# ---------------------------------------------------------------------------

@router.post("")
async def criar(user: dict = Depends(get_current_user)):
    envio = Envio.criar(user["id"])
    return envio.para_dict()


@router.get("/{envio_id}")
async def ver(envio_id: str, user: dict = Depends(get_current_user)):
    return _abrir(envio_id, user).para_dict()


@router.post("/{envio_id}/documentos")
async def adicionar_documentos(
    envio_id: str,
    arquivos: list[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    envio = _abrir(envio_id, user)
    entrada = await _receber(arquivos)
    try:
        await asyncio.to_thread(envio.adicionar_documentos, entrada)
    finally:
        shutil.rmtree(entrada, ignore_errors=True)
    return envio.para_dict()


@router.delete("/{envio_id}/documentos")
async def limpar_documentos(envio_id: str, user: dict = Depends(get_current_user)):
    envio = _abrir(envio_id, user)
    envio.limpar_documentos()
    return envio.para_dict()


@router.delete("/{envio_id}/faturas")
async def limpar_faturas(envio_id: str, user: dict = Depends(get_current_user)):
    envio = _abrir(envio_id, user)
    await asyncio.to_thread(envio.limpar_faturas)
    return envio.para_dict()


@router.delete("/{envio_id}/documentos/{doc_id}")
async def remover_documento(envio_id: str, doc_id: str, user: dict = Depends(get_current_user)):
    envio = _abrir(envio_id, user)
    try:
        envio.remover_documento(doc_id)
    except EnvioErro as e:
        raise HTTPException(status_code=404, detail=str(e))
    return envio.para_dict()


@router.post("/{envio_id}/documentos/mover-faturas")
async def mover_para_faturas(envio_id: str, body: Ids, user: dict = Depends(get_current_user)):
    envio = _abrir(envio_id, user)
    await asyncio.to_thread(envio.mover_documentos_para_faturas, body.ids)
    return envio.para_dict()


@router.post("/{envio_id}/faturas")
async def adicionar_faturas(
    envio_id: str,
    arquivos: list[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    envio = _abrir(envio_id, user)
    entrada = await _receber(arquivos)
    try:
        await asyncio.to_thread(envio.adicionar_faturas, entrada)
    finally:
        shutil.rmtree(entrada, ignore_errors=True)
    return envio.para_dict()


@router.delete("/{envio_id}/faturas/{fatura_id}")
async def remover_fatura(envio_id: str, fatura_id: str, user: dict = Depends(get_current_user)):
    envio = _abrir(envio_id, user)
    try:
        await asyncio.to_thread(envio.remover_fatura, fatura_id)
    except EnvioErro as e:
        raise HTTPException(status_code=404, detail=str(e))
    return envio.para_dict()


@router.post("/{envio_id}/faturas/ordem")
async def ordenar_faturas(envio_id: str, body: Ordem, user: dict = Depends(get_current_user)):
    envio = _abrir(envio_id, user)
    try:
        await asyncio.to_thread(envio.ordenar_faturas, body.modo, body.ids)
    except EnvioErro as e:
        raise HTTPException(status_code=400, detail=str(e))
    return envio.para_dict()


@router.get("/{envio_id}/faturas.pdf")
async def baixar_faturas(envio_id: str, user: dict = Depends(get_current_user)):
    envio = _abrir(envio_id, user)
    if not envio.pdf_faturas.exists():
        raise HTTPException(status_code=404, detail="Ainda não tem PDF de faturas.")
    return FileResponse(envio.pdf_faturas, media_type="application/pdf", filename=envio.pdf_faturas.name)


# ---------------------------------------------------------------------------
# Envio pro Drive
# ---------------------------------------------------------------------------

@router.post("/{envio_id}/pasta")
async def preparar_pasta(envio_id: str, body: DadosProcesso, user: dict = Depends(get_current_user)):
    envio = _abrir(envio_id, user)
    lock = _locks_pasta.setdefault(envio_id, asyncio.Lock())
    async with lock:
        try:
            async with DriveEscritorio() as drive:
                d = await drive.garantir_destino(body.autor, body.processo)
        except DriveErro as e:
            raise HTTPException(status_code=400, detail=str(e))
        envio.estado["destino"] = {
            **d.para_dict(),
            "drive_id": d.drive_id,
            "autor": body.autor,
            "processo": body.processo,
        }
        envio.salvar()
    return envio.para_dict()


@router.post("/{envio_id}/itens/{item_id}/subir")
async def subir_item(envio_id: str, item_id: str, user: dict = Depends(get_current_user)):
    envio = _abrir(envio_id, user)
    destino = envio.estado.get("destino")
    if not destino or not destino.get("subsidios_id"):
        raise HTTPException(status_code=400, detail="Crie a pasta do processo antes de subir.")
    try:
        caminho, nome = envio.caminho_item(item_id)
    except EnvioErro as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        async with DriveEscritorio() as drive:
            existente = await drive.arquivo_existente(nome, destino["subsidios_id"], destino["drive_id"])
            if existente:
                status, file_id = "ja_existia", existente["id"]
            else:
                file_id = await drive.enviar_arquivo(caminho, nome, destino["subsidios_id"])
                status = "enviado"
    except DriveErro as e:
        envio = _abrir(envio_id, user)
        envio.estado.setdefault("enviados", {})[item_id] = {"status": "erro", "msg": str(e)}
        envio.salvar()
        await registrar_envio(envio_id, user, envio.estado, len(envio.itens_para_subir()))
        raise HTTPException(status_code=502, detail=str(e))

    # Recarrega antes de gravar: outros uploads do mesmo envio rodam em paralelo
    envio = _abrir(envio_id, user)
    envio.estado.setdefault("enviados", {})[item_id] = {"status": status, "file_id": file_id}
    envio.salvar()
    await registrar_envio(envio_id, user, envio.estado, len(envio.itens_para_subir()))
    return {"item_id": item_id, "nome": nome, "status": status, "file_id": file_id}
