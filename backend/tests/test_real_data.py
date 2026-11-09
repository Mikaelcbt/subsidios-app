"""Teste com os dados reais enviados pelo Mikael."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.patterns import identificar_documento, TipoDocumento
from app.core.processor import processar_subsidios, relatorio_para_json
from app.core.patterns import ModalidadeContrato


def test_identificacao_dados_reais():
    """Identifica cada arquivo real e mostra o resultado."""
    # Pasta com os dados reais extraídos
    # Os nomes têm encoding unicode escapado, precisamos lidar com isso
    pasta = Path("/home/claude/subsidios-app/test-data")

    # Encontrar a subpasta (pode ter encoding diferente)
    subpastas = [d for d in pasta.iterdir() if d.is_dir()]
    if subpastas:
        pasta = subpastas[0]

    arquivos = sorted(pasta.iterdir())

    print(f"Total de arquivos: {len(arquivos)}\n")
    print(f"{'ARQUIVO':<65} {'TIPO':<40} {'CONTRATO':<15} {'CONFIANÇA'}")
    print("-" * 140)

    tipos_count = {}
    contratos = set()

    for arq in arquivos:
        if not arq.is_file():
            continue
        doc = identificar_documento(arq.name)
        tipo_label = doc.tipo.value
        tipos_count[tipo_label] = tipos_count.get(tipo_label, 0) + 1
        if doc.numero_contrato:
            contratos.add(doc.numero_contrato)

        nome_curto = arq.name[:63] if len(arq.name) > 63 else arq.name
        print(f"{nome_curto:<65} {tipo_label:<40} {doc.numero_contrato or '-':<15} {doc.confianca}")

    print(f"\n--- RESUMO ---")
    print(f"Contratos encontrados: {sorted(contratos)}")
    print(f"\nTipos de documento:")
    for tipo, count in sorted(tipos_count.items(), key=lambda x: -x[1]):
        print(f"  {tipo}: {count}")


def test_processamento_completo():
    """Roda o pipeline completo nos dados reais."""
    pasta_entrada = Path("/home/claude/subsidios-app/test-data")
    subpastas = [d for d in pasta_entrada.iterdir() if d.is_dir()]
    if subpastas:
        pasta_entrada = subpastas[0]

    pasta_saida = Path("/home/claude/subsidios-app/test-output")
    pasta_saida.mkdir(exist_ok=True)

    relatorio = processar_subsidios(
        pasta_entrada=pasta_entrada,
        pasta_saida=pasta_saida,
        autor="ROSINEIDE OLEGARIO DE ANDRADE",
        processo="0874410-08.2026.8",
        modalidade=ModalidadeContrato.EMPRESTIMO_CONSIGNADO,
        analisar_conteudo_pdf=False,  # Sem OCR por agora
    )

    print(f"\n=== RELATÓRIO DE PROCESSAMENTO ===")
    print(relatorio_para_json(relatorio))


if __name__ == "__main__":
    test_identificacao_dados_reais()
    test_processamento_completo()
