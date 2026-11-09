"""
Motor de extração: descompacta ZIPs (recursivo), extrai texto de PDFs,
e identifica documentos.
"""

import os
import zipfile
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import pdfplumber

from .patterns import (
    DocumentoIdentificado,
    TipoDocumento,
    identificar_documento,
    extrair_numero_contrato_do_nome,
    identificar_tipo_por_nome,
    REGEX_NUMERO_CONTRATO,
)


def descompactar_recursivo(caminho_entrada: Path, caminho_saida: Path) -> list[Path]:
    """Descompacta todos os ZIPs recursivamente até não sobrar nenhum.

    Retorna lista de todos os arquivos individuais extraídos.
    """
    caminho_saida.mkdir(parents=True, exist_ok=True)
    arquivos_finais = []

    # Copiar arquivos não-ZIP direto pra saída
    itens = list(caminho_entrada.iterdir()) if caminho_entrada.is_dir() else [caminho_entrada]

    for item in itens:
        if item.is_file():
            if item.suffix.lower() == '.zip':
                _extrair_zip_recursivo(item, caminho_saida, arquivos_finais)
            else:
                destino = caminho_saida / item.name
                destino = _nome_unico(destino)
                shutil.copy2(item, destino)
                arquivos_finais.append(destino)
        elif item.is_dir():
            sub_arquivos = descompactar_recursivo(item, caminho_saida)
            arquivos_finais.extend(sub_arquivos)

    return arquivos_finais


def _extrair_zip_recursivo(zip_path: Path, destino: Path, acumulador: list[Path]):
    """Extrai um ZIP e processa ZIPs internos recursivamente."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                zf.extractall(tmp_path)

                for item in tmp_path.rglob('*'):
                    if item.is_file():
                        if item.suffix.lower() == '.zip':
                            _extrair_zip_recursivo(item, destino, acumulador)
                        else:
                            final = destino / item.name
                            final = _nome_unico(final)
                            shutil.copy2(item, final)
                            acumulador.append(final)
    except zipfile.BadZipFile:
        # ZIP corrompido: mover como está e sinalizar
        final = destino / f"CORROMPIDO_{zip_path.name}"
        shutil.copy2(zip_path, final)
        acumulador.append(final)


def _nome_unico(caminho: Path) -> Path:
    """Se o arquivo já existe, adiciona sufixo numérico."""
    if not caminho.exists():
        return caminho
    base = caminho.stem
    ext = caminho.suffix
    contador = 1
    while True:
        novo = caminho.parent / f"{base}_{contador}{ext}"
        if not novo.exists():
            return novo
        contador += 1


def extrair_texto_pdf(caminho_pdf: Path, max_paginas: int = 5) -> str:
    """Extrai texto das primeiras páginas de um PDF.

    Usado para identificar número de contrato quando não está no nome.
    Limita a leitura para performance.
    """
    texto = ""
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            for i, pagina in enumerate(pdf.pages):
                if i >= max_paginas:
                    break
                texto_pagina = pagina.extract_text()
                if texto_pagina:
                    texto += texto_pagina + "\n"
    except Exception:
        pass
    return texto


def identificar_com_conteudo(doc: DocumentoIdentificado, caminho: Path) -> DocumentoIdentificado:
    """Tenta melhorar a identificação usando o conteúdo do PDF.

    Usado quando o nome do arquivo não foi suficiente para identificar
    o número do contrato.
    """
    if doc.numero_contrato and doc.confianca == "alta":
        return doc  # Já identificado com confiança

    if caminho.suffix.lower() != '.pdf':
        return doc

    texto = extrair_texto_pdf(caminho)
    if not texto:
        if doc.confianca != "alta":
            doc.confianca = "baixa"
            doc.observacao = "Não foi possível extrair texto do PDF"
        return doc

    # Tentar identificar tipo pelo conteúdo se ainda desconhecido
    if doc.tipo == TipoDocumento.DESCONHECIDO:
        tipo = identificar_tipo_por_nome(texto[:500])  # Primeiros 500 chars
        if tipo != TipoDocumento.DESCONHECIDO:
            doc.tipo = tipo
            doc.confianca = "media"
            doc.observacao = "Tipo identificado pelo conteúdo do PDF"

    # Tentar extrair número de contrato do conteúdo
    if doc.numero_contrato is None:
        matches = REGEX_NUMERO_CONTRATO.findall(texto)
        if matches:
            # Pegar o número mais frequente (provavelmente é o contrato)
            numeros_base = [m.split('-')[0] for m in matches]
            from collections import Counter
            mais_comum = Counter(numeros_base).most_common(1)[0][0]
            doc.numero_contrato = mais_comum
            doc.confianca = "media"
            doc.observacao = (doc.observacao + " | Contrato extraído do conteúdo do PDF").strip(" | ")

    return doc
