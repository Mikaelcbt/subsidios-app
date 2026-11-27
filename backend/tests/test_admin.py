"""Testes do papel de ADM e do registro de envios."""

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core import admin  # noqa: E402
from app.core.auth import get_current_user  # noqa: E402
from app.main import app  # noqa: E402


def _cliente(email):
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": email}
    return TestClient(app)


def test_me_e_bloqueio(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "mikaelcbt@gmail.com, outra@x.com")
    try:
        c = _cliente("MikaelCBT@gmail.com")
        assert c.get("/api/me").json()["admin"] is True
        c = _cliente("operador@x.com")
        assert c.get("/api/me").json()["admin"] is False
        assert c.get("/api/admin/usuarios").status_code == 403
        assert c.get("/api/admin/envios").status_code == 403
        assert c.get("/api/admin/drive").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_registrar_so_quando_completo(monkeypatch):
    monkeypatch.setattr(admin, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(admin, "SUPABASE_SERVICE_KEY", "k")
    enviados = []

    class Cliente(httpx.AsyncClient):
        def __init__(self, **kw):
            super().__init__(transport=httpx.MockTransport(
                lambda r: enviados.append(r) or httpx.Response(201)))

    monkeypatch.setattr(admin.httpx, "AsyncClient", Cliente)
    estado = {"destino": {"autor": "A", "processo": "1"}, "enviados": {"a": {"status": "enviado"}}}
    user = {"id": "u1", "email": "op@x.com"}
    asyncio.run(admin.registrar_envio("e1", user, estado, 2))
    assert enviados == []
    estado["enviados"]["b"] = {"status": "erro"}
    asyncio.run(admin.registrar_envio("e1", user, estado, 2))
    assert len(enviados) == 1
    import json
    corpo = json.loads(enviados[0].content)
    assert (corpo["enviados"], corpo["falhas"], corpo["total_itens"]) == (1, 1, 2)
    assert "merge-duplicates" in enviados[0].headers["Prefer"]
