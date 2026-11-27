"""Preparo de um envio pro Drive do escritório.

Um envio guarda, numa pasta temporária no servidor:
    documentos/     arquivos soltos (ZIPs já extraídos), sem renomear
    faturas/        PDFs de fatura recebidos (ZIPs já extraídos)
    FATURAS.pdf     todas as faturas juntadas num PDF só
    envio.json      estado (dono, lista de arquivos, ordem das faturas, destino)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from pypdf import PdfReader, PdfWriter

from .extractor import descompactar_recursivo, extrair_texto_pdf

ENVIOS_DIR = Path(os.getenv("ENVIOS_DIR", "/tmp/subsidios-envios"))
NOME_PDF_FATURAS = "FATURAS.pdf"
VALIDADE_HORAS = 24

# Lixo de sistema que vem dentro de ZIP e não deve subir
ARQUIVOS_IGNORADOS = {".ds_store", "thumbs.db", "desktop.ini"}

REGEX_FATURA = re.compile(r"FATURA", re.IGNORECASE)

# Áudios e vídeos vão pra uma subpasta dentro de SUBSÍDIOS (só criada se tiver áudio)
NOME_PASTA_AUDIOS = os.getenv("NOME_PASTA_AUDIOS", "ÁUDIOS")
EXTENSOES_AUDIO = {
    ".mp3", ".ogg", ".oga", ".opus", ".wav", ".m4a", ".aac", ".amr", ".wma",
    ".flac", ".3gp", ".3ga", ".aif", ".aiff", ".caf", ".webm", ".mpga",
    # Vídeos vão pra mesma pasta
    ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".wmv", ".mpg", ".mpeg", ".3g2",
    ".flv", ".ts", ".mts",
}


def eh_audio(nome: str) -> bool:
    return Path(nome).suffix.lower() in EXTENSOES_AUDIO

MESES = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}


class EnvioErro(Exception):
    pass


# ---------------------------------------------------------------------------
# Datas de fatura
# ---------------------------------------------------------------------------

def _data_valida(ano: int, mes: int, dia: int = 1) -> Optional[date]:
    if not (2000 <= ano <= 2100 and 1 <= mes <= 12):
        return None
    try:
        return date(ano, mes, dia)
    except ValueError:
        return date(ano, mes, 1)


def data_no_nome(nome: str) -> Optional[date]:
    """Acha mês/ano da fatura no nome do arquivo.

    Aceita: 2024-03-15, 20240315, 2024-03, 15/03/2024, 15-03-2024, 03-2024, 032024, MAR-2024, MARCO 2024.
    """
    base = Path(nome).stem.upper()
    from .drive_escritorio import sem_acento
    base = sem_acento(base)

    padroes = [
        (r"(?<!\d)(\d{4})[-_. ](\d{2})[-_. ](\d{2})(?!\d)", lambda m: _data_valida(int(m[1]), int(m[2]), int(m[3]))),
        (r"(?<!\d)(\d{2})[-_./ ](\d{2})[-_./ ](\d{4})(?!\d)", lambda m: _data_valida(int(m[3]), int(m[2]), int(m[1]))),
        (r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", lambda m: _data_valida(int(m[1]), int(m[2]), int(m[3]))),
        (r"(?<!\d)(\d{4})[-_. ](\d{2})(?!\d)", lambda m: _data_valida(int(m[1]), int(m[2]))),
        (r"(?<!\d)(\d{2})[-_./ ](\d{4})(?!\d)", lambda m: _data_valida(int(m[2]), int(m[1]))),
        (r"(?<!\d)(20\d{2})(\d{2})(?!\d)", lambda m: _data_valida(int(m[1]), int(m[2]))),
        (r"(?<!\d)(\d{2})(20\d{2})(?!\d)", lambda m: _data_valida(int(m[2]), int(m[1]))),
    ]
    for padrao, conv in padroes:
        for m in re.finditer(padrao, base):
            d = conv(m)
            if d:
                return d

    m = re.search(r"\b(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[A-Z]*[-_. /]*(\d{4}|\d{2})\b", base)
    if m:
        ano = int(m[2])
        ano = ano + 2000 if ano < 100 else ano
        return _data_valida(ano, MESES[m[1]])
    return None


def data_no_conteudo(caminho: Path) -> Optional[date]:
    """Procura a data de vencimento (ou a primeira data) na primeira página do PDF."""
    texto = extrair_texto_pdf(caminho, max_paginas=1)
    if not texto:
        return None
    m = re.search(r"VENCIMENTO[^0-9]{0,40}(\d{2})/(\d{2})/(\d{4})", texto, re.IGNORECASE)
    if not m:
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if m:
        return _data_valida(int(m[3]), int(m[2]), int(m[1]))
    return None


def _chave_nome(nome: str):
    """Ordenação natural: fatura 2 antes de fatura 10."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", nome)]


# ---------------------------------------------------------------------------
# Envio
# ---------------------------------------------------------------------------

class Envio:
    def __init__(self, envio_id: str) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", envio_id):
            raise EnvioErro("Envio inválido.")
        self.id = envio_id
        self.pasta = ENVIOS_DIR / envio_id
        self.dir_documentos = self.pasta / "documentos"
        self.dir_faturas = self.pasta / "faturas"
        self.pdf_faturas = self.pasta / NOME_PDF_FATURAS
        self._estado_path = self.pasta / "envio.json"
        self.estado: dict = {}

    # -- ciclo de vida -----------------------------------------------------

    @classmethod
    def criar(cls, user_id: str) -> "Envio":
        limpar_antigos()
        envio = cls(uuid.uuid4().hex)
        envio.dir_documentos.mkdir(parents=True)
        envio.dir_faturas.mkdir(parents=True)
        envio.estado = {
            "user_id": user_id,
            "criado_em": time.time(),
            "documentos": [],
            "faturas": [],
            "ordem_faturas": "data",
            "faturas_pdf": None,
            "destino": None,
            "enviados": {},
        }
        envio.salvar()
        return envio

    @classmethod
    def abrir(cls, envio_id: str, user_id: str) -> "Envio":
        envio = cls(envio_id)
        if not envio._estado_path.exists():
            raise EnvioErro("Envio não encontrado ou expirado. Comece de novo.")
        envio.estado = json.loads(envio._estado_path.read_text())
        if envio.estado.get("user_id") != user_id:
            raise EnvioErro("Envio não encontrado ou expirado. Comece de novo.")
        return envio

    def salvar(self) -> None:
        tmp = self._estado_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.estado, ensure_ascii=False))
        tmp.replace(self._estado_path)

    # -- entrada de arquivos -----------------------------------------------

    def _extrair(self, entradas: Path, destino: Path) -> list[Path]:
        arquivos = descompactar_recursivo(entradas, destino)
        finais = []
        for a in arquivos:
            if a.name.lower() in ARQUIVOS_IGNORADOS or a.name.startswith("._") or "__MACOSX" in a.parts:
                a.unlink(missing_ok=True)
                continue
            finais.append(a)
        return finais

    def adicionar_documentos(self, entradas: Path) -> list[dict]:
        novos = []
        for arq in self._extrair(entradas, self.dir_documentos):
            item = {
                "id": uuid.uuid4().hex[:12],
                "nome": arq.name,
                "tamanho": arq.stat().st_size,
                "parece_fatura": bool(REGEX_FATURA.search(arq.name)) and arq.suffix.lower() == ".pdf",
                "corrompido": arq.name.startswith("CORROMPIDO_"),
                "audio": eh_audio(arq.name),
            }
            self.estado["documentos"].append(item)
            novos.append(item)
        self.salvar()
        return novos

    def remover_documento(self, doc_id: str) -> None:
        docs = self.estado["documentos"]
        item = next((d for d in docs if d["id"] == doc_id), None)
        if not item:
            raise EnvioErro("Documento não encontrado.")
        (self.dir_documentos / item["nome"]).unlink(missing_ok=True)
        self.estado["documentos"] = [d for d in docs if d["id"] != doc_id]
        self.salvar()

    def limpar_documentos(self) -> None:
        shutil.rmtree(self.dir_documentos, ignore_errors=True)
        self.dir_documentos.mkdir(parents=True, exist_ok=True)
        ids = {d["id"] for d in self.estado["documentos"]}
        self.estado["documentos"] = []
        self.estado["enviados"] = {k: v for k, v in self.estado.get("enviados", {}).items() if k not in ids}
        self.salvar()

    def limpar_faturas(self) -> None:
        shutil.rmtree(self.dir_faturas, ignore_errors=True)
        self.dir_faturas.mkdir(parents=True, exist_ok=True)
        self.estado["faturas"] = []
        self.estado.get("enviados", {}).pop("faturas", None)
        self._juntar()

    def adicionar_faturas(self, entradas: Path) -> list[dict]:
        novos = []
        for arq in self._extrair(entradas, self.dir_faturas):
            novos.append(self._registrar_fatura(arq))
        self._juntar()
        return novos

    def mover_documentos_para_faturas(self, ids: list[str]) -> None:
        restantes = []
        for d in self.estado["documentos"]:
            if d["id"] in ids:
                origem = self.dir_documentos / d["nome"]
                if origem.exists():
                    from .extractor import _nome_unico
                    destino = _nome_unico(self.dir_faturas / d["nome"])
                    shutil.move(str(origem), destino)
                    self._registrar_fatura(destino)
            else:
                restantes.append(d)
        self.estado["documentos"] = restantes
        self._juntar()

    def _registrar_fatura(self, arq: Path) -> dict:
        item: dict = {
            "id": uuid.uuid4().hex[:12],
            "nome": arq.name,
            "tamanho": arq.stat().st_size,
            "paginas": 0,
            "data": None,
            "erro": None,
        }
        if arq.suffix.lower() != ".pdf":
            item["erro"] = "Não é PDF, não entra no arquivo juntado."
        else:
            try:
                item["paginas"] = len(PdfReader(str(arq)).pages)
            except Exception:
                item["erro"] = "PDF ilegível ou protegido, não entra no arquivo juntado."
            d = data_no_nome(arq.name) or (data_no_conteudo(arq) if not item["erro"] else None)
            item["data"] = d.isoformat() if d else None
        self.estado["faturas"].append(item)
        return item

    def remover_fatura(self, fatura_id: str) -> None:
        fats = self.estado["faturas"]
        item = next((f for f in fats if f["id"] == fatura_id), None)
        if not item:
            raise EnvioErro("Fatura não encontrada.")
        (self.dir_faturas / item["nome"]).unlink(missing_ok=True)
        self.estado["faturas"] = [f for f in fats if f["id"] != fatura_id]
        self._juntar()

    # -- ordem e junção ----------------------------------------------------

    def ordenar_faturas(self, modo: str, ids: Optional[list[str]] = None) -> None:
        """modo: 'data' (mais antiga primeiro), 'nome' ou 'manual' (usa ids na ordem dada)."""
        fats = self.estado["faturas"]
        if modo == "manual":
            if not ids or set(ids) != {f["id"] for f in fats}:
                raise EnvioErro("Ordem manual precisa listar todas as faturas.")
            pos = {i: n for n, i in enumerate(ids)}
            fats.sort(key=lambda f: pos[f["id"]])
        elif modo in ("data", "nome"):
            pass
        else:
            raise EnvioErro("Ordem inválida.")
        self.estado["ordem_faturas"] = modo
        self._juntar()

    def _aplicar_ordem(self) -> None:
        modo = self.estado.get("ordem_faturas", "data")
        fats = self.estado["faturas"]
        if modo == "nome":
            fats.sort(key=lambda f: _chave_nome(f["nome"]))
        elif modo == "data":
            # Com data primeiro (mais antiga -> mais nova), sem data no fim por nome
            fats.sort(key=lambda f: (f["data"] is None, f["data"] or "", _chave_nome(f["nome"])))

    def _juntar(self) -> None:
        self._aplicar_ordem()
        writer = PdfWriter()
        total = 0
        for f in self.estado["faturas"]:
            if f["erro"]:
                continue
            try:
                reader = PdfReader(str(self.dir_faturas / f["nome"]))
                for page in reader.pages:
                    writer.add_page(page)
                total += len(reader.pages)
            except Exception:
                f["erro"] = "PDF ilegível, ficou de fora."
        if total:
            with open(self.pdf_faturas, "wb") as fp:
                writer.write(fp)
            self.estado["faturas_pdf"] = {
                "nome": NOME_PDF_FATURAS,
                "paginas": total,
                "tamanho": self.pdf_faturas.stat().st_size,
                "gerado_em": time.time(),
            }
        else:
            self.pdf_faturas.unlink(missing_ok=True)
            self.estado["faturas_pdf"] = None
        self.salvar()

    # -- saída -------------------------------------------------------------

    def itens_para_subir(self) -> list[dict]:
        """Tudo que vai pra SUBSÍDIOS: documentos soltos + FATURAS.pdf (áudios na subpasta)."""
        itens = [
            {
                "id": d["id"],
                "nome": d["nome"],
                "tamanho": d["tamanho"],
                "tipo": "audio" if eh_audio(d["nome"]) else "documento",
                "subpasta": NOME_PASTA_AUDIOS if eh_audio(d["nome"]) else None,
            }
            for d in self.estado["documentos"]
        ]
        if self.estado.get("faturas_pdf"):
            fp = self.estado["faturas_pdf"]
            itens.append({"id": "faturas", "nome": fp["nome"], "tamanho": fp["tamanho"], "tipo": "faturas", "subpasta": None})
        return itens

    def caminho_item(self, item_id: str) -> tuple[Path, str]:
        if item_id == "faturas":
            if not self.estado.get("faturas_pdf") or not self.pdf_faturas.exists():
                raise EnvioErro("Ainda não tem PDF de faturas.")
            return self.pdf_faturas, NOME_PDF_FATURAS
        d = next((d for d in self.estado["documentos"] if d["id"] == item_id), None)
        if not d:
            raise EnvioErro("Arquivo não encontrado neste envio.")
        return self.dir_documentos / d["nome"], d["nome"]

    def para_dict(self) -> dict:
        return {
            "envio_id": self.id,
            "documentos": self.estado["documentos"],
            "faturas": self.estado["faturas"],
            "ordem_faturas": self.estado.get("ordem_faturas", "data"),
            "faturas_pdf": self.estado.get("faturas_pdf"),
            "itens_para_subir": self.itens_para_subir(),
            "nome_pasta_audios": NOME_PASTA_AUDIOS,
            "destino": self.estado.get("destino"),
            "enviados": self.estado.get("enviados", {}),
        }


def limpar_antigos() -> None:
    if not ENVIOS_DIR.exists():
        return
    limite = time.time() - VALIDADE_HORAS * 3600
    for p in ENVIOS_DIR.iterdir():
        try:
            if p.is_dir() and p.stat().st_mtime < limite:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass
