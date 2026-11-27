"""Acesso ao Google Drive do escritório (Drives compartilhados por faixa de letra).

A conexão é uma só para o escritório inteiro, não por usuário. Dois jeitos de configurar:

1. Conta de serviço (recomendado): GOOGLE_SERVICE_ACCOUNT_JSON com o JSON da chave
   (texto puro ou base64). O e-mail da conta de serviço precisa ser adicionado como
   participante ("Administrador de conteúdo") em cada Drive compartilhado da faixa.
2. Conta Google do escritório: GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET +
   GOOGLE_ESCRITORIO_REFRESH_TOKEN (refresh token com escopo drive de uma conta que já
   participa dos Drives). Útil se o Workspace bloquear participantes externos.

Estrutura esperada no Drive:
    CÍVEL- Pan T - V            (Drive compartilhado da faixa)
        T                       (pasta da letra, já existe)
            NOME DO AUTOR - 0000000-00.0000.0.00.0000
                SUBSÍDIOS
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

DRIVE_API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/drive"
FOLDER_MIME = "application/vnd.google-apps.folder"

NOME_SUBPASTA = "SUBSÍDIOS"

# Só Drives cujo nome contém esse texto entram no mapa de faixas (vazio = todos).
FILTRO_NOME_DRIVE = os.getenv("DRIVE_FAIXAS_FILTRO", "PAN")

# Faixa no fim do nome do Drive: "CÍVEL- Pan T - V" -> T, V
REGEX_FAIXA = re.compile(r"([A-Z])\s*-\s*([A-Z])\s*$")


class DriveErro(Exception):
    """Erro com mensagem pronta pra mostrar ao operador."""


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

def sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def normalizar(texto: str) -> str:
    """Maiúsculas, sem acento e com espaços simples. Pra comparar nomes."""
    return re.sub(r"\s+", " ", sem_acento(texto).upper()).strip()


def letra_inicial(autor: str) -> str:
    """Primeira letra do nome do autor, sem acento (Ítalo -> I)."""
    for c in normalizar(autor):
        if "A" <= c <= "Z":
            return c
    raise DriveErro("Nome do autor sem nenhuma letra.")


def formatar_processo(processo: str) -> str:
    """Formata no padrão CNJ quando vier só com os 20 dígitos. Senão devolve como veio."""
    processo = processo.strip()
    digitos = re.sub(r"\D", "", processo)
    if len(digitos) == 20 and not re.search(r"[.\-]", processo):
        d = digitos
        return f"{d[0:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:20]}"
    return re.sub(r"\s+", "", processo)


def nome_pasta_processo(autor: str, processo: str) -> str:
    """NOME DO AUTOR - NÚMERO DO PROCESSO (autor em maiúsculas, mantendo acentos)."""
    autor_fmt = re.sub(r"\s+", " ", autor).strip().upper()
    return f"{autor_fmt} - {formatar_processo(processo)}"


def digitos_processo(processo: str) -> str:
    return re.sub(r"\D", "", processo)


def _q(valor: str) -> str:
    """Escapa texto pra usar dentro de aspas simples na busca do Drive."""
    return valor.replace("\\", "\\\\").replace("'", "\\'")


# ---------------------------------------------------------------------------
# Credenciais
# ---------------------------------------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _carregar_conta_servico() -> Optional[dict]:
    bruto = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not bruto:
        return None
    if not bruto.startswith("{"):
        try:
            bruto = base64.b64decode(bruto).decode()
        except Exception as e:
            raise DriveErro("GOOGLE_SERVICE_ACCOUNT_JSON não é JSON nem base64 válido.") from e
    try:
        info = json.loads(bruto)
    except json.JSONDecodeError as e:
        raise DriveErro("GOOGLE_SERVICE_ACCOUNT_JSON com JSON inválido.") from e
    if "private_key" not in info or "client_email" not in info:
        raise DriveErro("GOOGLE_SERVICE_ACCOUNT_JSON sem private_key ou client_email.")
    return info


def modo_configurado() -> Optional[str]:
    if os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip():
        return "conta_servico"
    if (
        os.getenv("GOOGLE_ESCRITORIO_REFRESH_TOKEN", "").strip()
        and os.getenv("GOOGLE_CLIENT_ID")
        and os.getenv("GOOGLE_CLIENT_SECRET")
    ):
        return "conta_escritorio"
    return None


class Credenciais:
    """Gera e guarda em cache o access token do escritório."""

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._expira: float = 0.0
        self.email: Optional[str] = None

    async def token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._expira - 300:
            return self._token

        modo = modo_configurado()
        if modo == "conta_servico":
            dados = await self._token_conta_servico(client)
        elif modo == "conta_escritorio":
            dados = await self._token_refresh(client)
        else:
            raise DriveErro(
                "Drive do escritório não configurado. Falta GOOGLE_SERVICE_ACCOUNT_JSON no servidor."
            )

        self._token = dados["access_token"]
        self._expira = time.time() + int(dados.get("expires_in", 3600))
        return self._token

    async def _token_conta_servico(self, client: httpx.AsyncClient) -> dict:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        info = _carregar_conta_servico()
        assert info is not None
        self.email = info["client_email"]
        agora = int(time.time())
        token_uri = info.get("token_uri", TOKEN_URL)
        header = {"alg": "RS256", "typ": "JWT"}
        claims = {
            "iss": info["client_email"],
            "scope": SCOPE,
            "aud": token_uri,
            "iat": agora,
            "exp": agora + 3600,
        }
        assinatura_base = (
            _b64url(json.dumps(header).encode()) + "." + _b64url(json.dumps(claims).encode())
        )
        chave = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
        assinatura = chave.sign(assinatura_base.encode(), padding.PKCS1v15(), hashes.SHA256())
        jwt = assinatura_base + "." + _b64url(assinatura)

        resp = await client.post(
            token_uri,
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt},
        )
        if resp.status_code != 200:
            raise DriveErro(f"Google recusou a conta de serviço: {resp.text[:200]}")
        return resp.json()

    async def _token_refresh(self, client: httpx.AsyncClient) -> dict:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
                "refresh_token": os.getenv("GOOGLE_ESCRITORIO_REFRESH_TOKEN", ""),
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code != 200:
            raise DriveErro(
                "Google recusou o refresh token do escritório (pode ter expirado). "
                f"Resposta: {resp.text[:200]}"
            )
        return resp.json()


_credenciais = Credenciais()


# ---------------------------------------------------------------------------
# Cliente do Drive
# ---------------------------------------------------------------------------

@dataclass
class Faixa:
    drive_id: str
    nome: str
    de: str
    ate: str

    def cobre(self, letra: str) -> bool:
        return self.de <= letra <= self.ate


@dataclass
class Destino:
    """Onde os arquivos de um processo vão parar."""
    drive_id: str
    drive_nome: str
    letra: str
    letra_id: str
    pasta_nome: str
    pasta_id: Optional[str] = None          # None = ainda não existe
    subsidios_id: Optional[str] = None      # None = ainda não existe
    avisos: list[str] = field(default_factory=list)

    @property
    def caminho(self) -> str:
        return f"{self.drive_nome} / {self.letra} / {self.pasta_nome} / {NOME_SUBPASTA}"

    @property
    def url(self) -> Optional[str]:
        alvo = self.subsidios_id or self.pasta_id
        return f"https://drive.google.com/drive/folders/{alvo}" if alvo else None

    def para_dict(self) -> dict:
        return {
            "drive": self.drive_nome,
            "letra": self.letra,
            "pasta_processo": self.pasta_nome,
            "subpasta": NOME_SUBPASTA,
            "caminho": self.caminho,
            "pasta_existe": self.pasta_id is not None,
            "subsidios_existe": self.subsidios_id is not None,
            "pasta_id": self.pasta_id,
            "subsidios_id": self.subsidios_id,
            "url": self.url,
            "avisos": self.avisos,
        }


_cache_faixas: tuple[float, list[Faixa]] = (0.0, [])


class DriveEscritorio:
    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        credenciais: Optional[Credenciais] = None,
    ) -> None:
        self._client = client
        self._cred = credenciais or _credenciais

    async def __aenter__(self) -> "DriveEscritorio":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0))
            self._proprio = True
        else:
            self._proprio = False
        return self

    async def __aexit__(self, *exc) -> None:
        if self._proprio and self._client is not None:
            await self._client.aclose()

    @property
    def email(self) -> Optional[str]:
        return self._cred.email

    # -- HTTP --------------------------------------------------------------

    async def _req(self, method: str, url: str, **kwargs) -> httpx.Response:
        assert self._client is not None
        token = await self._cred.token(self._client)
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        params = kwargs.pop("params", {})
        params.setdefault("supportsAllDrives", "true")
        for tentativa in range(4):
            resp = await self._client.request(method, url, headers=headers, params=params, **kwargs)
            if resp.status_code in (429, 500, 502, 503, 504) and tentativa < 3:
                await _dormir(2 ** tentativa)
                continue
            break
        if resp.status_code >= 400:
            raise DriveErro(_mensagem_erro(resp))
        return resp

    async def _listar(self, q: str, drive_id: str, campos: str = "id,name,size") -> list[dict]:
        itens: list[dict] = []
        page_token = None
        while True:
            params = {
                "q": q,
                "corpora": "drive",
                "driveId": drive_id,
                "includeItemsFromAllDrives": "true",
                "fields": f"nextPageToken,files({campos})",
                "pageSize": "1000",
            }
            if page_token:
                params["pageToken"] = page_token
            dados = (await self._req("GET", f"{DRIVE_API}/files", params=params)).json()
            itens.extend(dados.get("files", []))
            page_token = dados.get("nextPageToken")
            if not page_token:
                return itens

    # -- Faixas ------------------------------------------------------------

    async def faixas(self, usar_cache: bool = True) -> list[Faixa]:
        global _cache_faixas
        if usar_cache and _cache_faixas[1] and time.time() - _cache_faixas[0] < 600:
            return _cache_faixas[1]

        drives: list[dict] = []
        page_token = None
        while True:
            params = {"pageSize": "100", "fields": "nextPageToken,drives(id,name)"}
            if page_token:
                params["pageToken"] = page_token
            dados = (await self._req("GET", f"{DRIVE_API}/drives", params=params)).json()
            drives.extend(dados.get("drives", []))
            page_token = dados.get("nextPageToken")
            if not page_token:
                break

        resultado: list[Faixa] = []
        filtro = normalizar(FILTRO_NOME_DRIVE)
        for d in drives:
            nome_norm = normalizar(d["name"])
            if filtro and filtro not in nome_norm:
                continue
            m = REGEX_FAIXA.search(nome_norm)
            if not m:
                continue
            resultado.append(Faixa(drive_id=d["id"], nome=d["name"], de=m.group(1), ate=m.group(2)))

        resultado.sort(key=lambda f: f.de)
        _cache_faixas = (time.time(), resultado)
        return resultado

    async def faixa_da_letra(self, letra: str) -> Faixa:
        faixas = await self.faixas()
        candidatas = [f for f in faixas if f.cobre(letra)]
        if not candidatas:
            # Pode ser cache velho: tenta de novo sem cache
            faixas = await self.faixas(usar_cache=False)
            candidatas = [f for f in faixas if f.cobre(letra)]
        if not candidatas:
            vistos = ", ".join(f.nome for f in faixas) or "nenhum"
            raise DriveErro(
                f"Nenhum Drive compartilhado cobre a letra {letra}. "
                f"Drives que o app enxerga: {vistos}. Confira se a conta do app foi adicionada nele."
            )
        return candidatas[0]

    # -- Pastas ------------------------------------------------------------

    async def _pastas_em(self, parent_id: str, drive_id: str) -> list[dict]:
        q = f"'{_q(parent_id)}' in parents and mimeType = '{FOLDER_MIME}' and trashed = false"
        return await self._listar(q, drive_id, campos="id,name")

    async def criar_pasta(self, nome: str, parent_id: str) -> str:
        resp = await self._req(
            "POST",
            f"{DRIVE_API}/files",
            params={"fields": "id"},
            json={"name": nome, "mimeType": FOLDER_MIME, "parents": [parent_id]},
        )
        return resp.json()["id"]

    async def resolver_destino(self, autor: str, processo: str) -> Destino:
        """Descobre onde a pasta do processo fica, sem criar nada."""
        if not autor.strip():
            raise DriveErro("Informe o nome do autor.")
        if not digitos_processo(processo):
            raise DriveErro("Informe o número do processo.")

        letra = letra_inicial(autor)
        faixa = await self.faixa_da_letra(letra)

        pastas_raiz = await self._pastas_em(faixa.drive_id, faixa.drive_id)
        letra_pasta = next((p for p in pastas_raiz if normalizar(p["name"]) == letra), None)
        if not letra_pasta:
            raise DriveErro(f"Não achei a pasta da letra {letra} dentro de {faixa.nome}.")

        destino = Destino(
            drive_id=faixa.drive_id,
            drive_nome=faixa.nome,
            letra=letra,
            letra_id=letra_pasta["id"],
            pasta_nome=nome_pasta_processo(autor, processo),
        )

        # Reusa pasta que já tem esse número de processo no nome
        alvo = digitos_processo(processo)
        pastas = await self._pastas_em(letra_pasta["id"], faixa.drive_id)
        iguais = [p for p in pastas if alvo in re.sub(r"\D", "", p["name"])]
        if iguais:
            exata = next((p for p in iguais if normalizar(p["name"]) == normalizar(destino.pasta_nome)), None)
            escolhida = exata or iguais[0]
            destino.pasta_id = escolhida["id"]
            destino.pasta_nome = escolhida["name"]
            if len(iguais) > 1:
                destino.avisos.append(
                    f"Existem {len(iguais)} pastas com esse processo na letra {letra}. Vou usar \"{escolhida['name']}\"."
                )
            if not exata and normalizar(escolhida["name"]) != normalizar(nome_pasta_processo(autor, processo)):
                destino.avisos.append(
                    f"Já existe uma pasta desse processo com nome diferente: \"{escolhida['name']}\". Vou usar ela."
                )

            subpastas = await self._pastas_em(destino.pasta_id, faixa.drive_id)
            sub = next((p for p in subpastas if normalizar(p["name"]) == normalizar(NOME_SUBPASTA)), None)
            if sub:
                destino.subsidios_id = sub["id"]

        return destino

    async def garantir_destino(self, autor: str, processo: str) -> Destino:
        """Resolve e cria o que faltar (pasta do processo e SUBSÍDIOS)."""
        destino = await self.resolver_destino(autor, processo)
        if destino.pasta_id is None:
            destino.pasta_id = await self.criar_pasta(destino.pasta_nome, destino.letra_id)
        if destino.subsidios_id is None:
            destino.subsidios_id = await self.criar_pasta(NOME_SUBPASTA, destino.pasta_id)
        return destino

    # -- Arquivos ----------------------------------------------------------

    async def arquivo_existente(self, nome: str, parent_id: str, drive_id: str) -> Optional[dict]:
        q = (
            f"'{_q(parent_id)}' in parents and name = '{_q(nome)}' "
            f"and mimeType != '{FOLDER_MIME}' and trashed = false"
        )
        itens = await self._listar(q, drive_id)
        return itens[0] if itens else None

    async def enviar_arquivo(self, caminho: Path, nome: str, parent_id: str) -> str:
        """Upload resumable (aguenta arquivos grandes). Retorna o ID do arquivo."""
        assert self._client is not None
        tamanho = caminho.stat().st_size
        mime = _mime(nome)
        inicio = await self._req(
            "POST",
            UPLOAD_API,
            params={"uploadType": "resumable", "fields": "id"},
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": mime,
                "X-Upload-Content-Length": str(tamanho),
            },
            json={"name": nome, "parents": [parent_id]},
        )
        sessao = inicio.headers.get("Location")
        if not sessao:
            raise DriveErro("Google não devolveu a URL de upload.")

        with open(caminho, "rb") as f:
            conteudo = f.read()
        for tentativa in range(4):
            resp = await self._client.put(
                sessao,
                content=conteudo,
                headers={"Content-Type": mime, "Content-Length": str(tamanho)},
                timeout=httpx.Timeout(600.0, connect=15.0),
            )
            if resp.status_code in (500, 502, 503, 504) and tentativa < 3:
                await _dormir(2 ** tentativa)
                continue
            break
        if resp.status_code >= 400:
            raise DriveErro(_mensagem_erro(resp))
        return resp.json()["id"]


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

async def _dormir(segundos: float) -> None:
    import asyncio
    await asyncio.sleep(segundos)


def _mime(nome: str) -> str:
    import mimetypes
    tipo, _ = mimetypes.guess_type(nome)
    return tipo or "application/octet-stream"


def _mensagem_erro(resp: httpx.Response) -> str:
    try:
        erro = resp.json().get("error", {})
        msg = erro.get("message") if isinstance(erro, dict) else str(erro)
    except Exception:
        msg = resp.text[:200]
    if resp.status_code == 403:
        return f"Sem permissão no Drive ({msg}). A conta do app precisa ser participante do Drive compartilhado."
    if resp.status_code == 404:
        return f"Pasta ou Drive não encontrado ({msg}). A conta do app pode não ter acesso."
    return f"Erro do Google Drive ({resp.status_code}): {msg}"
