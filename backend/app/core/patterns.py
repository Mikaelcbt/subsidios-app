"""
Padrões de nomenclatura e regras de identificação de documentos.
Baseado nos padrões reais observados nos arquivos do banco.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TipoDocumento(Enum):
    CONTRATO = "Contrato"
    CONTRATO_CANCELADO = "Contrato Cancelado"
    DEMONSTRATIVO_OP = "Demonstrativo de Operações"
    PROPOSTA = "Proposta"
    PLANILHA_PROPOSTA = "Planilha de Proposta"
    TED_DOC = "TED/DOC"
    TERMO_AUTORIZACAO = "Termo de Autorização para Acesso a Dados"
    AUTORIZACAO_PREVIDENCIA = "Autorização de Acesso aos Dados da Previdência Social"
    LAUDO = "Laudo"
    FATURA = "Fatura"
    BIOMETRIA_FACIAL = "Biometria Facial"
    PANCRED_HISTORICO = "PANCRED - Histórico de Contratos"
    DOCUMENTOS_CONTRATACAO = "Documentos Apresentados no Momento da Contratação"
    EXTRATO_CARTAO = "Extrato de Cartão"
    EXTRATO_EVOLUTIVO = "Extrato Evolutivo"
    RG = "RG / Documento de Identidade"
    TELA_SISTEMA = "Tela do Sistema"
    TELA_SMS = "Tela SMS"
    TELA_DESBLOQUEIO = "Tela Desbloqueio Cartão"
    TELA_CONTRATOS = "Tela Contratos Possuídos"
    DESCONHECIDO = "Desconhecido"


class ModalidadeContrato(Enum):
    CARTAO_CONSIGNADO = "Cartão Consignado"
    EMPRESTIMO_CONSIGNADO = "Empréstimo Consignado"


@dataclass
class DocumentoIdentificado:
    nome_original: str
    tipo: TipoDocumento
    numero_contrato: Optional[str] = None
    confianca: str = "alta"  # alta, media, baixa
    observacao: str = ""


# Regex para extrair número de contrato de nomes de arquivo
# Padrão: sequência de 6+ dígitos, opcionalmente seguida de -dígito(s)
# Ignora números entre parênteses como (1), (2) que são sufixos de cópia
REGEX_NUMERO_CONTRATO = re.compile(r'(?<!\()(\d{6,}(?:-\d{1,2})?)(?!\))')

# Padrões de nome de arquivo -> tipo de documento
# Ordem importa: padrões mais específicos primeiro
PADROES_NOME_ARQUIVO = [
    # Padrões compostos (mais específicos primeiro)
    (re.compile(r'DEMONSTRATIVO\s+DE\s+OP', re.IGNORECASE), TipoDocumento.DEMONSTRATIVO_OP),
    (re.compile(r'TED\s*DOC', re.IGNORECASE), TipoDocumento.TED_DOC),
    (re.compile(r'\bTED\b', re.IGNORECASE), TipoDocumento.TED_DOC),
    (re.compile(r'TERMO\s+DE\s+AUTORIZA', re.IGNORECASE), TipoDocumento.TERMO_AUTORIZACAO),
    (re.compile(r'AUTORIZA.*ACESSO.*DADOS.*PREVID', re.IGNORECASE), TipoDocumento.AUTORIZACAO_PREVIDENCIA),
    (re.compile(r'AUTORIZA.*PREVID', re.IGNORECASE), TipoDocumento.AUTORIZACAO_PREVIDENCIA),
    (re.compile(r'PANCRED.*HIST', re.IGNORECASE), TipoDocumento.PANCRED_HISTORICO),
    (re.compile(r'DOCUMENTOS\s+APRESENTADOS', re.IGNORECASE), TipoDocumento.DOCUMENTOS_CONTRATACAO),
    (re.compile(r'BIOMETRIA\s+FACIAL', re.IGNORECASE), TipoDocumento.BIOMETRIA_FACIAL),
    (re.compile(r'EXTRATO\s+EVOLUTIVO', re.IGNORECASE), TipoDocumento.EXTRATO_EVOLUTIVO),
    (re.compile(r'EXTRATO\s+DE?\s*CART', re.IGNORECASE), TipoDocumento.EXTRATO_CARTAO),
    (re.compile(r'PLANILHA\s+DE\s+PROPOSTA', re.IGNORECASE), TipoDocumento.PLANILHA_PROPOSTA),
    (re.compile(r'CONTRATO\s+CANCELADO', re.IGNORECASE), TipoDocumento.CONTRATO_CANCELADO),
    (re.compile(r'TELA\s+CONTRATOS\s+POSSU', re.IGNORECASE), TipoDocumento.TELA_CONTRATOS),
    (re.compile(r'TELA\s+DESBLOQUEIO', re.IGNORECASE), TipoDocumento.TELA_DESBLOQUEIO),
    (re.compile(r'TELA\s+SMS', re.IGNORECASE), TipoDocumento.TELA_SMS),
    (re.compile(r'\bLAUDO\b', re.IGNORECASE), TipoDocumento.LAUDO),
    (re.compile(r'\bPROPOSTA\b', re.IGNORECASE), TipoDocumento.PROPOSTA),
    (re.compile(r'\bFATURA', re.IGNORECASE), TipoDocumento.FATURA),
    (re.compile(r'\bRG\b', re.IGNORECASE), TipoDocumento.RG),
    # "CONTRATO" por último pois aparece em muitos nomes compostos
    (re.compile(r'\bCONTRATO\b', re.IGNORECASE), TipoDocumento.CONTRATO),
]

# Documentos que NÃO pertencem a um contrato específico (são gerais do processo)
TIPOS_GERAIS = {
    TipoDocumento.BIOMETRIA_FACIAL,
    TipoDocumento.PANCRED_HISTORICO,
    TipoDocumento.DOCUMENTOS_CONTRATACAO,
    TipoDocumento.RG,
    TipoDocumento.AUTORIZACAO_PREVIDENCIA,
    TipoDocumento.EXTRATO_EVOLUTIVO,
    TipoDocumento.TELA_SMS,
    TipoDocumento.TELA_DESBLOQUEIO,
    TipoDocumento.TELA_CONTRATOS,
    TipoDocumento.TELA_SISTEMA,
}

# Checklist de documentos essenciais por modalidade
CHECKLIST_CARTAO_CONSIGNADO = [
    TipoDocumento.CONTRATO,
    TipoDocumento.TED_DOC,
    TipoDocumento.EXTRATO_CARTAO,
    TipoDocumento.FATURA,
]

CHECKLIST_EMPRESTIMO_CONSIGNADO = [
    TipoDocumento.CONTRATO,
    TipoDocumento.TED_DOC,
    TipoDocumento.DEMONSTRATIVO_OP,
]

# Documentos importantes em ambas as modalidades (não obrigatórios, mas relevantes)
DOCUMENTOS_IMPORTANTES = [
    TipoDocumento.LAUDO,
    TipoDocumento.PROPOSTA,
    TipoDocumento.TERMO_AUTORIZACAO,
]


def identificar_tipo_por_nome(nome_arquivo: str) -> TipoDocumento:
    """Identifica o tipo de documento pelo nome do arquivo."""
    for padrao, tipo in PADROES_NOME_ARQUIVO:
        if padrao.search(nome_arquivo):
            return tipo
    return TipoDocumento.DESCONHECIDO


def extrair_numero_contrato_do_nome(nome_arquivo: str) -> Optional[str]:
    """Extrai o número do contrato do nome do arquivo.

    Retorna o número base (sem sufixo -X) para agrupamento.
    Ex: '383951465-4' -> '383951465'
        '351408900' -> '351408900'
    Ignora sufixos de cópia como (1), (2).
    """
    # Remover sufixo de cópia tipo (1), (2) antes de buscar
    nome_limpo = re.sub(r'\(\d+\)', '', nome_arquivo)
    # Remover extensão
    nome_limpo = re.sub(r'\.\w{2,4}$', '', nome_limpo)

    match = REGEX_NUMERO_CONTRATO.search(nome_limpo)
    if match:
        numero = match.group(1)
        return numero.split('-')[0] if '-' in numero else numero
    return None


def identificar_documento(nome_arquivo: str) -> DocumentoIdentificado:
    """Identifica tipo e contrato de um documento pelo nome do arquivo."""
    tipo = identificar_tipo_por_nome(nome_arquivo)

    if tipo in TIPOS_GERAIS:
        return DocumentoIdentificado(
            nome_original=nome_arquivo,
            tipo=tipo,
            numero_contrato=None,
            confianca="alta",
            observacao="Documento geral do processo"
        )

    numero = extrair_numero_contrato_do_nome(nome_arquivo)

    if tipo == TipoDocumento.DESCONHECIDO:
        confianca = "baixa"
        obs = "Tipo não identificado pelo nome"
    elif numero is None and tipo != TipoDocumento.DESCONHECIDO:
        confianca = "media"
        obs = "Tipo identificado mas sem número de contrato no nome"
    else:
        confianca = "alta"
        obs = ""

    return DocumentoIdentificado(
        nome_original=nome_arquivo,
        tipo=tipo,
        numero_contrato=numero,
        confianca=confianca,
        observacao=obs
    )
