"""Testes do envio pro Drive do escritório (Drive falso em memória, sem rede)."""

import asyncio
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core import envio as envio_mod  # noqa: E402
from app.core.drive_escritorio import (  # noqa: E402
    Credenciais,
    DriveErro,
    DriveEscritorio,
    formatar_processo,
    letra_inicial,
    nome_pasta_processo,
)
from app.core.envio import Envio, data_no_nome  # noqa: E402

FOLDER = "application/vnd.google-apps.folder"


# ---------------------------------------------------------------------------
# Funções puras
# ---------------------------------------------------------------------------

def test_letra_inicial():
    assert letra_inicial("Lívia França") == "L"
    assert letra_inicial("  Ítalo Souza") == "I"
    assert letra_inicial("Érica") == "E"
    assert letra_inicial("teresinha de jesus") == "T"


def test_nome_pasta():
    assert nome_pasta_processo("Teresinha de Jesus  Moura", "0844498-70.2025.8.18.0140") == (
        "TERESINHA DE JESUS MOURA - 0844498-70.2025.8.18.0140"
    )
    assert formatar_processo("08444987020258180140") == "0844498-70.2025.8.18.0140"
    assert formatar_processo(" 0844498-70.2025.8.18.0140 ") == "0844498-70.2025.8.18.0140"


@pytest.mark.parametrize(
    "nome,esperado",
    [
        ("FATURA 2024-03-15.pdf", "2024-03-15"),
        ("fatura_15-03-2024.pdf", "2024-03-15"),
        ("FATURA 03-2024.pdf", "2024-03-01"),
        ("FATURA_202403.pdf", "2024-03-01"),
        ("fatura 032024.pdf", "2024-03-01"),
        ("Fatura Março 2024.pdf", "2024-03-01"),
        ("FATURA SET-23.pdf", "2023-09-01"),
        ("FATURA 123456789.pdf", None),
    ],
)
def test_data_no_nome(nome, esperado):
    d = data_no_nome(nome)
    assert (d.isoformat() if d else None) == esperado


# ---------------------------------------------------------------------------
# Drive falso
# ---------------------------------------------------------------------------

class DriveFalso:
    def __init__(self):
        self.arquivos: dict[str, dict] = {}
        self.drives = []
        self.uploads: dict[str, dict] = {}
        self.n = 0

    def novo_id(self):
        self.n += 1
        return f"id{self.n}"

    def add_drive(self, nome, letras):
        did = self.novo_id()
        self.drives.append({"id": did, "name": nome})
        for l in letras:
            self.add(l, did, FOLDER)
        return did

    def add(self, nome, parent, mime="application/pdf", size=10):
        fid = self.novo_id()
        self.arquivos[fid] = {"id": fid, "name": nome, "parents": [parent], "mimeType": mime, "size": str(size)}
        return fid

    def filhos(self, parent, nome=None):
        return [
            f for f in self.arquivos.values()
            if parent in f["parents"] and (nome is None or f["name"] == nome)
        ]

    def handler(self, req: httpx.Request) -> httpx.Response:
        url = req.url
        p = url.path
        if p == "/drive/v3/drives":
            return httpx.Response(200, json={"drives": self.drives})
        if p == "/drive/v3/files" and req.method == "GET":
            q = parse_qs(urlparse(str(url)).query)["q"][0]
            parent = re.search(r"'([^']+)' in parents", q).group(1)
            itens = self.filhos(parent)
            m = re.search(r"name = '((?:[^'\\]|\\.)*)'", q)
            if m:
                nome = m.group(1).replace("\\'", "'").replace("\\\\", "\\")
                itens = [f for f in itens if f["name"] == nome]
            if f"mimeType = '{FOLDER}'" in q:
                itens = [f for f in itens if f["mimeType"] == FOLDER]
            if f"mimeType != '{FOLDER}'" in q:
                itens = [f for f in itens if f["mimeType"] != FOLDER]
            return httpx.Response(200, json={"files": itens})
        if p == "/drive/v3/files" and req.method == "POST":
            body = json.loads(req.content)
            fid = self.add(body["name"], body["parents"][0], body["mimeType"])
            return httpx.Response(200, json={"id": fid})
        if p == "/upload/drive/v3/files" and req.method == "POST":
            body = json.loads(req.content)
            sid = self.novo_id()
            self.uploads[sid] = body
            return httpx.Response(200, headers={"Location": f"https://upload.test/sessao/{sid}"})
        if p.startswith("/sessao/") and req.method == "PUT":
            body = self.uploads.pop(p.split("/")[-1])
            fid = self.add(body["name"], body["parents"][0], size=len(req.content))
            return httpx.Response(200, json={"id": fid})
        return httpx.Response(404, json={"error": {"message": f"rota falsa {req.method} {p}"}})


class CredFalsa(Credenciais):
    async def token(self, client):
        return "tok"


@pytest.fixture
def fake():
    import app.core.drive_escritorio as de
    de._cache_faixas = (0.0, [])
    f = DriveFalso()
    f.add_drive("Cível - PAN", [])
    f.add_drive("CÍVEL- Pan A - C", ["A", "B", "C"])
    f.tv = f.add_drive("CÍVEL- Pan T - V", ["T", "U", "V"])
    f.add_drive("CÍVEL- Pan J - L", ["J", "K", "L"])
    return f


def _drive(fake):
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    return DriveEscritorio(client=client, credenciais=CredFalsa())


def test_cria_pasta_e_subsidios(fake):
    async def run():
        async with _drive(fake) as d:
            dest = await d.resolver_destino("Teresinha de Jesus Moura", "0844498-70.2025.8.18.0140")
            assert dest.drive_nome == "CÍVEL- Pan T - V"
            assert dest.letra == "T"
            assert dest.pasta_id is None
            dest = await d.garantir_destino("Teresinha de Jesus Moura", "0844498-70.2025.8.18.0140")
            return dest

    dest = asyncio.run(run())
    pasta = fake.arquivos[dest.pasta_id]
    assert pasta["name"] == "TERESINHA DE JESUS MOURA - 0844498-70.2025.8.18.0140"
    assert fake.arquivos[pasta["parents"][0]]["name"] == "T"
    assert fake.arquivos[dest.subsidios_id]["name"] == "SUBSÍDIOS"
    assert dest.caminho == "CÍVEL- Pan T - V / T / TERESINHA DE JESUS MOURA - 0844498-70.2025.8.18.0140 / SUBSÍDIOS"


def test_reusa_pasta_existente_com_nome_diferente(fake):
    letra_t = next(f["id"] for f in fake.arquivos.values() if f["name"] == "T" and fake.tv in f["parents"])
    existente = fake.add("TERESINHA J MOURA  0844498-70.2025.8.18.0140", letra_t, FOLDER)
    sub = fake.add("SUBSIDIOS", existente, FOLDER)

    async def run():
        async with _drive(fake) as d:
            return await d.garantir_destino("Teresinha de Jesus Moura", "08444987020258180140")

    dest = asyncio.run(run())
    assert dest.pasta_id == existente
    assert dest.subsidios_id == sub
    assert dest.avisos  # avisa que o nome é diferente
    assert len([f for f in fake.arquivos.values() if f["mimeType"] == FOLDER]) == 11  # nada novo


def test_letra_sem_drive(fake):
    async def run():
        async with _drive(fake) as d:
            await d.resolver_destino("Zuleide", "0844498-70.2025.8.18.0140")

    with pytest.raises(DriveErro, match="letra Z"):
        asyncio.run(run())


def test_upload_e_existente(fake, tmp_path):
    arq = tmp_path / "Contrato 123.pdf"
    arq.write_bytes(b"%PDF-1.4 teste")

    async def run():
        async with _drive(fake) as d:
            dest = await d.garantir_destino("Lívia França", "0000001-00.2025.8.18.0001")
            fid = await d.enviar_arquivo(arq, arq.name, dest.subsidios_id)
            existe = await d.arquivo_existente("Contrato 123.pdf", dest.subsidios_id, dest.drive_id)
            return dest, fid, existe

    dest, fid, existe = asyncio.run(run())
    assert fake.arquivos[fid]["parents"] == [dest.subsidios_id]
    assert existe["id"] == fid
    assert dest.drive_nome == "CÍVEL- Pan J - L"


# ---------------------------------------------------------------------------
# Envio local (extração e faturas)
# ---------------------------------------------------------------------------

def _pdf(paginas: int) -> bytes:
    w = PdfWriter()
    for _ in range(paginas):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_envio_documentos_e_faturas(tmp_path, monkeypatch):
    monkeypatch.setattr(envio_mod, "ENVIOS_DIR", tmp_path / "envios")
    e = Envio.criar("user1")

    entrada = tmp_path / "in1"
    entrada.mkdir()
    interno = io.BytesIO()
    with zipfile.ZipFile(interno, "w") as z:
        z.writestr("TED DOC - CONTRATO 1.pdf", _pdf(1))
        z.writestr("__MACOSX/._lixo", b"x")
    with zipfile.ZipFile(entrada / "subsidios.zip", "w") as z:
        z.writestr("pasta/Contrato 1.pdf", _pdf(2))
        z.writestr("pasta/FATURA 2024-02.pdf", _pdf(1))
        z.writestr("interno.zip", interno.getvalue())
        z.writestr(".DS_Store", b"x")
    (entrada / "RG.jpg").write_bytes(b"jpg")
    e.adicionar_documentos(entrada)

    nomes = sorted(d["nome"] for d in e.estado["documentos"])
    assert nomes == ["Contrato 1.pdf", "FATURA 2024-02.pdf", "RG.jpg", "TED DOC - CONTRATO 1.pdf"]
    suspeita = [d for d in e.estado["documentos"] if d["parece_fatura"]]
    assert [d["nome"] for d in suspeita] == ["FATURA 2024-02.pdf"]

    entrada2 = tmp_path / "in2"
    entrada2.mkdir()
    with zipfile.ZipFile(entrada2 / "faturas.zip", "w") as z:
        z.writestr("FATURA 2024-03.pdf", _pdf(3))
        z.writestr("FATURA 2024-01.pdf", _pdf(1))
        z.writestr("sem data.pdf", _pdf(2))
    e.adicionar_faturas(entrada2)
    e.mover_documentos_para_faturas([suspeita[0]["id"]])

    ordem = [f["nome"] for f in e.estado["faturas"]]
    assert ordem == ["FATURA 2024-01.pdf", "FATURA 2024-02.pdf", "FATURA 2024-03.pdf", "sem data.pdf"]
    assert e.estado["faturas_pdf"]["paginas"] == 7
    assert len(PdfReader(str(e.pdf_faturas)).pages) == 7

    ids = [f["id"] for f in e.estado["faturas"]][::-1]
    e.ordenar_faturas("manual", ids)
    assert [f["nome"] for f in e.estado["faturas"]][0] == "sem data.pdf"

    itens = e.itens_para_subir()
    assert [i["nome"] for i in itens if i["tipo"] == "faturas"] == ["FATURAS.pdf"]
    assert len(itens) == 4  # 3 documentos + FATURAS.pdf

    with pytest.raises(envio_mod.EnvioErro):
        Envio.abrir(e.id, "outro-user")


# ---------------------------------------------------------------------------
# Conta de serviço e rotas
# ---------------------------------------------------------------------------

def test_token_conta_servico(monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = chave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    monkeypatch.setenv(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        json.dumps({"client_email": "app@proj.iam.gserviceaccount.com", "private_key": pem,
                    "token_uri": "https://oauth2.googleapis.com/token"}),
    )
    recebido = {}

    def handler(req):
        recebido.update(parse_qs(req.content.decode()))
        return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            cred = Credenciais()
            return await cred.token(c), cred.email

    tok, email = asyncio.run(run())
    assert tok == "abc" and email == "app@proj.iam.gserviceaccount.com"
    assert recebido["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
    assert recebido["assertion"][0].count(".") == 2


def test_rotas_fluxo_completo(fake, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.api.envio_routes as rotas
    from app.main import app

    monkeypatch.setattr(envio_mod, "ENVIOS_DIR", tmp_path / "envios")
    monkeypatch.setattr(rotas, "DriveEscritorio", lambda: _drive(fake))
    monkeypatch.setattr(rotas, "modo_configurado", lambda: "conta_servico")
    c = TestClient(app)
    h = {"Authorization": "Bearer x"}

    st = c.get("/api/envios/drive/status", headers=h).json()
    assert [f["de"] for f in st["faixas"]] == ["A", "J", "T"]

    eid = c.post("/api/envios", headers=h).json()["envio_id"]
    r = c.post(f"/api/envios/{eid}/documentos", headers=h,
               files=[("arquivos", ("Contrato 9.pdf", _pdf(1), "application/pdf"))]).json()
    assert r["documentos"][0]["nome"] == "Contrato 9.pdf"
    r = c.post(f"/api/envios/{eid}/faturas", headers=h,
               files=[("arquivos", ("FATURA 01-2024.pdf", _pdf(2), "application/pdf"))]).json()
    assert r["faturas_pdf"]["paginas"] == 2
    assert c.get(f"/api/envios/{eid}/faturas.pdf", headers=h).content.startswith(b"%PDF")

    dados = {"autor": "Tales de Carvalho", "processo": "4002609-37.2026.8.26.0272"}
    dest = c.get("/api/envios/destino", headers=h, params=dados).json()
    assert dest["pasta_existe"] is False and dest["letra"] == "T"
    r = c.post(f"/api/envios/{eid}/pasta", headers=h, json=dados).json()
    assert r["destino"]["subsidios_id"]

    status = [c.post(f"/api/envios/{eid}/itens/{i['id']}/subir", headers=h).json()["status"]
              for i in r["itens_para_subir"]]
    assert status == ["enviado", "enviado"]
    # Reenvio não duplica
    again = c.post(f"/api/envios/{eid}/itens/faturas/subir", headers=h).json()
    assert again["status"] == "ja_existia"
    nomes = sorted(f["name"] for f in fake.filhos(r["destino"]["subsidios_id"]))
    assert nomes == ["Contrato 9.pdf", "FATURAS.pdf"]


def test_modo_teste_meu_drive(monkeypatch):
    import app.core.drive_escritorio as de
    de._cache_faixas = (0.0, [])
    f = DriveFalso()
    raiz = f.add("SUBSIDIOS TESTE", "meu-drive", FOLDER)
    faixa = f.add("CÍVEL- Pan T - V", raiz, FOLDER)
    letra_t = f.add("T", faixa, FOLDER)
    f.add("anotacoes.txt", raiz)
    monkeypatch.setattr(de, "RAIZ_TESTE_ID", raiz)

    async def run():
        async with _drive(f) as d:
            faixas = await d.faixas(usar_cache=False)
            dest = await d.garantir_destino("Tales de Carvalho", "4002609-37.2026.8.26.0272")
            return faixas, dest

    faixas, dest = asyncio.run(run())
    assert [(x.nome, x.drive_id) for x in faixas] == [("CÍVEL- Pan T - V", None)]
    assert dest.drive_id is None
    assert f.arquivos[dest.pasta_id]["parents"] == [letra_t]
    assert f.arquivos[dest.subsidios_id]["name"] == "SUBSÍDIOS"
    de._cache_faixas = (0.0, [])


def test_limpar_tudo(tmp_path, monkeypatch):
    monkeypatch.setattr(envio_mod, "ENVIOS_DIR", tmp_path / "envios")
    e = Envio.criar("u")
    entrada = tmp_path / "in"
    entrada.mkdir()
    (entrada / "a.pdf").write_bytes(_pdf(1))
    (entrada / "FATURA 01-2024.pdf").write_bytes(_pdf(2))
    e.adicionar_documentos(entrada)
    e.adicionar_faturas(entrada)
    assert e.estado["documentos"] and e.estado["faturas_pdf"]
    e.limpar_documentos()
    e.limpar_faturas()
    assert e.estado["documentos"] == [] and e.estado["faturas"] == []
    assert e.estado["faturas_pdf"] is None and not e.pdf_faturas.exists()
    assert list(e.dir_documentos.iterdir()) == [] and list(e.dir_faturas.iterdir()) == []
    assert e.itens_para_subir() == []


def test_audios_vao_pra_subpasta(fake, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.api.envio_routes as rotas
    from app.main import app

    monkeypatch.setattr(envio_mod, "ENVIOS_DIR", tmp_path / "envios")
    monkeypatch.setattr(rotas, "DriveEscritorio", lambda: _drive(fake))
    c = TestClient(app)
    h = {"Authorization": "Bearer x"}
    eid = c.post("/api/envios", headers=h).json()["envio_id"]
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("ligacao 1.mp3", b"ID3")
        z.writestr("audio whatsapp.OPUS", b"OggS")
        z.writestr("video chamada.MP4", b"ftyp")
    r = c.post(f"/api/envios/{eid}/documentos", headers=h, files=[
        ("arquivos", ("Contrato 1.pdf", _pdf(1), "application/pdf")),
        ("arquivos", ("audios.zip", zbuf.getvalue(), "application/zip")),
    ]).json()
    assert sorted(d["nome"] for d in r["documentos"] if d["audio"]) == ["audio whatsapp.OPUS", "ligacao 1.mp3", "video chamada.MP4"]

    dados = {"autor": "Tales", "processo": "4002609-37.2026.8.26.0272"}
    r = c.post(f"/api/envios/{eid}/pasta", headers=h, json=dados).json()
    for i in r["itens_para_subir"]:
        assert c.post(f"/api/envios/{eid}/itens/{i['id']}/subir", headers=h).json()["status"] == "enviado"

    sub = r["destino"]["subsidios_id"]
    filhos = {f["name"]: f for f in fake.filhos(sub)}
    assert set(filhos) == {"Contrato 1.pdf", "ÁUDIOS"}
    assert sorted(f["name"] for f in fake.filhos(filhos["ÁUDIOS"]["id"])) == ["audio whatsapp.OPUS", "ligacao 1.mp3", "video chamada.MP4"]
    assert len([f for f in fake.filhos(sub) if f["name"] == "ÁUDIOS"]) == 1


def test_sem_audio_nao_cria_subpasta(fake, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.api.envio_routes as rotas
    from app.main import app

    monkeypatch.setattr(envio_mod, "ENVIOS_DIR", tmp_path / "envios")
    monkeypatch.setattr(rotas, "DriveEscritorio", lambda: _drive(fake))
    c = TestClient(app)
    h = {"Authorization": "Bearer x"}
    eid = c.post("/api/envios", headers=h).json()["envio_id"]
    c.post(f"/api/envios/{eid}/documentos", headers=h,
           files=[("arquivos", ("Contrato 1.pdf", _pdf(1), "application/pdf"))])
    r = c.post(f"/api/envios/{eid}/pasta", headers=h, json={"autor": "Tales", "processo": "1234567-00.2026.8.26.0001"}).json()
    for i in r["itens_para_subir"]:
        c.post(f"/api/envios/{eid}/itens/{i['id']}/subir", headers=h)
    assert [f["name"] for f in fake.filhos(r["destino"]["subsidios_id"])] == ["Contrato 1.pdf"]


@pytest.mark.parametrize(
    "nome,conteudo,esperado",
    [
        ("gravacao", b"ID3\x03\x00" + b"\x00" * 20, True),
        ("ligacao.dat", b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 8, True),
        ("audio.bin", b"\xff\xfb\x90\x64" + b"\x00" * 20, True),
        ("zap", b"OggS" + b"\x00" * 20, True),
        ("video", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8, True),
        ("foto.HEIC", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 8, False),
        ("CHAMADA.WAV", b"qualquer", True),
        ("Contrato 1.pdf", b"%PDF-1.4", False),
        ("foto.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 12, False),
        ("sem_ext_texto", b"ola mundo nada demais", False),
    ],
)
def test_parece_midia(tmp_path, nome, conteudo, esperado):
    p = tmp_path / nome
    p.write_bytes(conteudo)
    assert envio_mod.parece_midia(p) is esperado
