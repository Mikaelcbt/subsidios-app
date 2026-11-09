"""Testes para a identificação de documentos pelos nomes reais observados."""

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from app.core.patterns import (
    identificar_documento,
    identificar_tipo_por_nome,
    extrair_numero_contrato_do_nome,
    TipoDocumento,
)


def test_nomes_reais():
    """Testa com os nomes exatos dos prints do Mikael."""
    casos = [
        ("Contrato 383951465-4", TipoDocumento.CONTRATO, "383951465"),
        ("DEMONSTRATIVO DE OP - CONTRATO 351408900-6", TipoDocumento.DEMONSTRATIVO_OP, "351408900"),
        ("DEMONSTRATIVO DE OP - CONTRATO 372223181-2", TipoDocumento.DEMONSTRATIVO_OP, "372223181"),
        ("DEMONSTRATIVO DE OP - CONTRATO 383951465-4", TipoDocumento.DEMONSTRATIVO_OP, "383951465"),
        ("Laudo - Contrato 372223181", TipoDocumento.LAUDO, "372223181"),
        ("Proposta 351408900", TipoDocumento.PROPOSTA, "351408900"),
        ("Proposta 372223181", TipoDocumento.PROPOSTA, "372223181"),
        ("Proposta 383951465", TipoDocumento.PROPOSTA, "383951465"),
        ("TED DOC - CONTRATO 351408900", TipoDocumento.TED_DOC, "351408900"),
        ("TED DOC - CONTRATO 372223181", TipoDocumento.TED_DOC, "372223181"),
        ("TED DOC - CONTRATO 383951465", TipoDocumento.TED_DOC, "383951465"),
        ("TERMO DE AUTORIZAÇÃO PARA ACESSO A DADOS - 372223181", TipoDocumento.TERMO_AUTORIZACAO, "372223181"),
        ("TERMO DE AUTORIZAÇÃO PARA ACESSO A DADOS - 383951465", TipoDocumento.TERMO_AUTORIZACAO, "383951465"),
        ("BIOMETRIA FACIAL", TipoDocumento.BIOMETRIA_FACIAL, None),
        ("PANCRED - HISTÓRICO DE CONTRATOS", TipoDocumento.PANCRED_HISTORICO, None),
        ("DOCUMENTOS APRESENTADOS NO MOMENTO DA CONTRATAÇÃO", TipoDocumento.DOCUMENTOS_CONTRATACAO, None),
    ]

    erros = []
    for nome, tipo_esperado, contrato_esperado in casos:
        doc = identificar_documento(nome)

        if doc.tipo != tipo_esperado:
            erros.append(f"TIPO: '{nome}' -> esperado {tipo_esperado.value}, got {doc.tipo.value}")

        if doc.numero_contrato != contrato_esperado:
            erros.append(f"CONTRATO: '{nome}' -> esperado {contrato_esperado}, got {doc.numero_contrato}")

    if erros:
        for e in erros:
            print(f"  FALHA: {e}")
        return False

    print(f"  OK: {len(casos)} nomes testados com sucesso")
    return True


def test_documentos_gerais():
    """Documentos gerais não devem ter contrato associado."""
    gerais = [
        "BIOMETRIA FACIAL",
        "PANCRED - HISTÓRICO DE CONTRATOS",
        "DOCUMENTOS APRESENTADOS NO MOMENTO DA CONTRATAÇÃO",
    ]

    for nome in gerais:
        doc = identificar_documento(nome)
        assert doc.numero_contrato is None, f"{nome} não deveria ter contrato"
        assert doc.confianca == "alta", f"{nome} deveria ter confiança alta"

    print(f"  OK: {len(gerais)} documentos gerais validados")
    return True


if __name__ == "__main__":
    print("Testando padrões de identificação...")
    ok = True
    ok = test_nomes_reais() and ok
    ok = test_documentos_gerais() and ok

    if ok:
        print("\nTodos os testes passaram!")
    else:
        print("\nAlguns testes falharam!")
        exit(1)
