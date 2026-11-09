"""
Organizador: monta a estrutura de pastas, separa documentos por contrato,
consolida faturas e gera relatório de conferência.
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pypdf import PdfWriter, PdfReader

from .patterns import (
    DocumentoIdentificado,
    TipoDocumento,
    ModalidadeContrato,
    TIPOS_GERAIS,
    CHECKLIST_CARTAO_CONSIGNADO,
    CHECKLIST_EMPRESTIMO_CONSIGNADO,
    DOCUMENTOS_IMPORTANTES,
)


@dataclass
class ResultadoConferencia:
    contrato: str
    documento: str
    tipo: TipoDocumento
    resultado: str  # "Localizado", "Não localizado", "Conferência manual"
    observacao: str = ""


@dataclass
class RelatorioProcessamento:
    autor: str
    processo: str
    contratos_encontrados: list[str] = field(default_factory=list)
    documentos_identificados: list[DocumentoIdentificado] = field(default_factory=list)
    documentos_nao_identificados: list[DocumentoIdentificado] = field(default_factory=list)
    conferencia: list[ResultadoConferencia] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    pasta_saida: str = ""


def organizar_documentos(
    documentos: list[tuple[Path, DocumentoIdentificado]],
    pasta_saida: Path,
    autor: str,
    processo: str,
    modalidade: ModalidadeContrato = ModalidadeContrato.EMPRESTIMO_CONSIGNADO,
) -> RelatorioProcessamento:
    """Organiza documentos na estrutura de pastas padrão e gera relatório.

    Estrutura:
    AUTOR - PROCESSO/
        subsídios/
            FATURAS CONSOLIDADAS.pdf
            Contrato XXXXX/
                [documentos do contrato]
            _gerais/
                [documentos sem contrato específico]
    """
    relatorio = RelatorioProcessamento(autor=autor, processo=processo)

    # Pasta principal: AUTOR - PROCESSO
    nome_pasta = f"{autor} - {processo}"
    pasta_principal = pasta_saida / nome_pasta
    pasta_subsidios = pasta_principal / "subsídios"
    pasta_subsidios.mkdir(parents=True, exist_ok=True)
    relatorio.pasta_saida = str(pasta_principal)

    # Separar por contrato
    por_contrato: dict[str, list[tuple[Path, DocumentoIdentificado]]] = {}
    gerais: list[tuple[Path, DocumentoIdentificado]] = []
    sem_contrato: list[tuple[Path, DocumentoIdentificado]] = []
    faturas: list[Path] = []

    for caminho, doc in documentos:
        if doc.tipo == TipoDocumento.FATURA:
            faturas.append(caminho)
            relatorio.documentos_identificados.append(doc)
        elif doc.tipo in TIPOS_GERAIS:
            gerais.append((caminho, doc))
            relatorio.documentos_identificados.append(doc)
        elif doc.numero_contrato:
            por_contrato.setdefault(doc.numero_contrato, []).append((caminho, doc))
            relatorio.documentos_identificados.append(doc)
        elif doc.confianca == "baixa":
            sem_contrato.append((caminho, doc))
            relatorio.documentos_nao_identificados.append(doc)
        else:
            sem_contrato.append((caminho, doc))
            relatorio.documentos_identificados.append(doc)

    relatorio.contratos_encontrados = sorted(por_contrato.keys())

    # Criar pastas por contrato e copiar arquivos
    for numero, docs in por_contrato.items():
        pasta_contrato = pasta_subsidios / f"Contrato {numero}"
        pasta_contrato.mkdir(parents=True, exist_ok=True)

        for caminho, doc in docs:
            destino = pasta_contrato / caminho.name
            shutil.copy2(caminho, destino)

    # Documentos gerais na raiz de subsídios
    for caminho, doc in gerais:
        destino = pasta_subsidios / caminho.name
        shutil.copy2(caminho, destino)

    # Documentos sem contrato identificado -> pasta de conferência manual
    if sem_contrato:
        pasta_manual = pasta_subsidios / "_conferência_manual"
        pasta_manual.mkdir(parents=True, exist_ok=True)
        for caminho, doc in sem_contrato:
            destino = pasta_manual / caminho.name
            shutil.copy2(caminho, destino)
        relatorio.alertas.append(
            f"{len(sem_contrato)} documento(s) precisam de conferência manual (contrato não identificado)"
        )

    # Consolidar faturas em PDF único
    if faturas:
        consolidar_faturas(faturas, pasta_subsidios / "FATURAS CONSOLIDADAS.pdf")

    # Conferência dos documentos essenciais
    relatorio.conferencia = conferir_documentos(por_contrato, modalidade)

    return relatorio


def consolidar_faturas(faturas: list[Path], saida: Path) -> bool:
    """Consolida todas as faturas em um único PDF."""
    try:
        writer = PdfWriter()
        for fatura in sorted(faturas, key=lambda f: f.name):
            try:
                reader = PdfReader(str(fatura))
                for page in reader.pages:
                    writer.add_page(page)
            except Exception:
                # Fatura ilegível, pular mas registrar
                continue

        if len(writer.pages) > 0:
            with open(saida, 'wb') as f:
                writer.write(f)
            return True
    except Exception:
        pass
    return False


def conferir_documentos(
    por_contrato: dict[str, list[tuple[Path, "DocumentoIdentificado"]]],
    modalidade: ModalidadeContrato,
) -> list[ResultadoConferencia]:
    """Confere se cada contrato tem os documentos essenciais."""

    if modalidade == ModalidadeContrato.CARTAO_CONSIGNADO:
        checklist = CHECKLIST_CARTAO_CONSIGNADO
    else:
        checklist = CHECKLIST_EMPRESTIMO_CONSIGNADO

    resultados = []

    for numero, docs in por_contrato.items():
        tipos_encontrados = {doc.tipo for _, doc in docs}
        confiancas = {doc.tipo: doc for _, doc in docs}

        for tipo_esperado in checklist:
            if tipo_esperado in tipos_encontrados:
                doc = confiancas[tipo_esperado]
                if doc.confianca == "alta":
                    resultado = "Localizado"
                else:
                    resultado = "Conferência manual"

                resultados.append(ResultadoConferencia(
                    contrato=numero,
                    documento=tipo_esperado.value,
                    tipo=tipo_esperado,
                    resultado=resultado,
                    observacao=doc.observacao if doc.confianca != "alta" else "",
                ))
            else:
                resultados.append(ResultadoConferencia(
                    contrato=numero,
                    documento=tipo_esperado.value,
                    tipo=tipo_esperado,
                    resultado="Não localizado",
                ))

        # Documentos importantes (não obrigatórios)
        for tipo_imp in DOCUMENTOS_IMPORTANTES:
            if tipo_imp in tipos_encontrados:
                resultados.append(ResultadoConferencia(
                    contrato=numero,
                    documento=tipo_imp.value,
                    tipo=tipo_imp,
                    resultado="Localizado",
                ))

    return resultados
