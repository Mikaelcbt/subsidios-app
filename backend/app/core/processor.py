"""
Processador principal: orquestra todo o pipeline.
Entrada -> Descompactação -> Identificação -> Organização -> Relatório
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional

from .extractor import descompactar_recursivo, identificar_com_conteudo
from .organizer import organizar_documentos, RelatorioProcessamento
from .patterns import (
    identificar_documento,
    ModalidadeContrato,
    TipoDocumento,
)


def processar_subsidios(
    pasta_entrada: Path,
    pasta_saida: Path,
    autor: str,
    processo: str,
    modalidade: ModalidadeContrato = ModalidadeContrato.EMPRESTIMO_CONSIGNADO,
    analisar_conteudo_pdf: bool = True,
) -> RelatorioProcessamento:
    """Pipeline completo de processamento de subsídios.

    Args:
        pasta_entrada: Pasta com ZIPs e arquivos individuais
        pasta_saida: Pasta onde será criada a estrutura organizada
        autor: Nome do autor do processo
        processo: Número do processo
        modalidade: Tipo de contrato para checklist
        analisar_conteudo_pdf: Se True, tenta extrair info do conteúdo dos PDFs

    Returns:
        RelatorioProcessamento com todos os resultados
    """
    # 1. Descompactar tudo
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        arquivos = descompactar_recursivo(pasta_entrada, tmp_path)

        # 2. Identificar cada documento
        documentos = []
        for arquivo in arquivos:
            doc = identificar_documento(arquivo.name)

            # 3. Se necessário, analisar conteúdo do PDF
            if analisar_conteudo_pdf:
                doc = identificar_com_conteudo(doc, arquivo)

            documentos.append((arquivo, doc))

        # 4. Organizar na estrutura de pastas e gerar relatório
        relatorio = organizar_documentos(
            documentos=documentos,
            pasta_saida=pasta_saida,
            autor=autor,
            processo=processo,
            modalidade=modalidade,
        )

    return relatorio


def relatorio_para_dict(relatorio: RelatorioProcessamento) -> dict:
    """Converte o relatório para dicionário serializável."""
    return {
        "autor": relatorio.autor,
        "processo": relatorio.processo,
        "processado_em": datetime.now().isoformat(),
        "contratos_encontrados": relatorio.contratos_encontrados,
        "total_documentos": len(relatorio.documentos_identificados),
        "total_nao_identificados": len(relatorio.documentos_nao_identificados),
        "alertas": relatorio.alertas,
        "pasta_saida": relatorio.pasta_saida,
        "documentos": [
            {
                "nome": d.nome_original,
                "tipo": d.tipo.value,
                "contrato": d.numero_contrato,
                "confianca": d.confianca,
                "observacao": d.observacao,
            }
            for d in relatorio.documentos_identificados
        ],
        "nao_identificados": [
            {
                "nome": d.nome_original,
                "tipo": d.tipo.value,
                "confianca": d.confianca,
                "observacao": d.observacao,
            }
            for d in relatorio.documentos_nao_identificados
        ],
        "conferencia": [
            {
                "contrato": c.contrato,
                "documento": c.documento,
                "resultado": c.resultado,
                "observacao": c.observacao,
            }
            for c in relatorio.conferencia
        ],
    }


def relatorio_para_json(relatorio: RelatorioProcessamento) -> str:
    """Gera JSON formatado do relatório."""
    return json.dumps(relatorio_para_dict(relatorio), indent=2, ensure_ascii=False)
