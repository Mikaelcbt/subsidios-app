"""
API FastAPI para processamento de subsídios.
Recebe uploads, processa e retorna relatório + arquivos organizados.
"""

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from ..core.processor import processar_subsidios, relatorio_para_dict
from ..core.patterns import ModalidadeContrato

router = APIRouter(prefix="/api", tags=["subsidios"])

# Diretório temporário para processamento
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/subsidios-uploads"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/subsidios-output"))


@router.post("/processar")
async def processar(
    arquivos: list[UploadFile] = File(...),
    autor: str = Form(...),
    processo: str = Form(...),
    modalidade: str = Form("emprestimo_consignado"),
):
    """Recebe arquivos (ZIPs e/ou PDFs), processa e retorna relatório."""

    # Criar diretórios temporários únicos para este job
    job_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{processo.replace('.', '_')}"
    pasta_entrada = UPLOAD_DIR / job_id
    pasta_saida = OUTPUT_DIR / job_id
    pasta_entrada.mkdir(parents=True, exist_ok=True)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    try:
        # Salvar uploads
        for arq in arquivos:
            destino = pasta_entrada / arq.filename
            with open(destino, "wb") as f:
                content = await arq.read()
                f.write(content)

        # Determinar modalidade
        mod = (
            ModalidadeContrato.CARTAO_CONSIGNADO
            if modalidade == "cartao_consignado"
            else ModalidadeContrato.EMPRESTIMO_CONSIGNADO
        )

        # Processar
        relatorio = processar_subsidios(
            pasta_entrada=pasta_entrada,
            pasta_saida=pasta_saida,
            autor=autor,
            processo=processo,
            modalidade=mod,
            analisar_conteudo_pdf=True,
        )

        # Gerar ZIP de saída
        zip_saida = pasta_saida / f"{job_id}_organizado.zip"
        shutil.make_archive(
            str(zip_saida.with_suffix("")),
            "zip",
            pasta_saida,
            relatorio.pasta_saida.split("/")[-1] if relatorio.pasta_saida else job_id,
        )

        resultado = relatorio_para_dict(relatorio)
        resultado["job_id"] = job_id
        resultado["download_url"] = f"/api/download/{job_id}"

        return JSONResponse(content=resultado)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Limpar pasta de entrada (manter saída para download)
        shutil.rmtree(pasta_entrada, ignore_errors=True)


@router.get("/download/{job_id}")
async def download(job_id: str):
    """Download do ZIP com os arquivos organizados."""
    zip_path = OUTPUT_DIR / job_id / f"{job_id}_organizado.zip"

    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado ou expirado")

    return FileResponse(
        path=str(zip_path),
        filename=f"subsidios_organizados_{job_id}.zip",
        media_type="application/zip",
    )


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
